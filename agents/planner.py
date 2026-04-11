from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions, ResultMessage,
    AssistantMessage, SystemMessage, TextBlock, ToolUseBlock, ToolResultBlock,
)
from config import MODEL, WORKSPACE_DIR, SPECS_DIR, MAX_PLANNER_TURNS
from pathlib import Path


PROMPTS_DIR = Path("prompts")

# ANSI colors
C_RESET = "\033[0m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_MAGENTA = "\033[35m"
C_DIM = "\033[2m"
C_BOLD = "\033[1m"


def _log(prefix: str, color: str, msg: str) -> None:
    from harness import _tee
    _tee(f"{color}[{prefix}]{C_RESET} {msg}")


def _prompt_user_question(tool_input: dict) -> str:
    """Display AskUserQuestion to the user in terminal and collect answer."""
    questions = tool_input.get("questions", [])

    parts = []
    for q in questions:
        question_text = q.get("question", "")
        options = q.get("options", [])
        multi = q.get("multiSelect", False)

        print(flush=True)
        print(f"{C_BOLD}{C_CYAN}  ? {question_text}{C_RESET}", flush=True)

        if options:
            for i, opt in enumerate(options):
                label = opt.get("label", "")
                desc = opt.get("description", "")
                print(f"    {C_GREEN}{i + 1}.{C_RESET} {label}", flush=True)
                if desc:
                    print(f"       {C_DIM}{desc}{C_RESET}", flush=True)

            if multi:
                print(f"    {C_DIM}(多选，用逗号分隔编号。直接回车跳过){C_RESET}", flush=True)
            else:
                print(f"    {C_DIM}(输入编号选择，或直接输入自定义回答){C_RESET}", flush=True)

        user_input = input(f"\n  {C_YELLOW}>{C_RESET} ").strip()

        if options and user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(options):
                parts.append(f"{question_text} -> {options[idx].get('label', user_input)}")
            else:
                parts.append(f"{question_text} -> {user_input}")
        elif options and multi and "," in user_input:
            selected = []
            for p in user_input.split(","):
                p = p.strip()
                if p.isdigit():
                    idx = int(p) - 1
                    if 0 <= idx < len(options):
                        selected.append(options[idx].get("label", p))
            parts.append(f"{question_text} -> {', '.join(selected) if selected else user_input}")
        else:
            parts.append(f"{question_text} -> {user_input if user_input else '(skipped)'}")

    return "\n".join(parts)


def _log_message(message) -> None:
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                text = block.text
                if len(text) > 300:
                    text = text[:300] + "..."
                _log("Planner", C_MAGENTA, text)
            elif isinstance(block, ToolUseBlock):
                if block.name != "AskUserQuestion":
                    inp = str(block.input)
                    if len(inp) > 120:
                        inp = inp[:120] + "..."
                    _log("Tool", C_YELLOW, f"{block.name}({inp})")
            elif isinstance(block, ToolResultBlock):
                status = "ERROR" if block.is_error else "OK"
                content = str(block.content or "")
                if len(content) > 200:
                  content = content[:200] + "..."
                _log("Result", C_GREEN if status == "OK" else C_YELLOW, f"[{status}] {content}")
    elif isinstance(message, ResultMessage):
        cost = f"${message.total_cost_usd:.2f}" if message.total_cost_usd else "?"
        _log("Planner", C_GREEN, f"Done. turns={message.num_turns} cost={cost} duration={message.duration_ms // 1000}s")
        if message.is_error:
            _log("Planner", C_YELLOW, f"ERROR: {message.result}")


async def run_planner(user_prompt: str, resume_session_id: str | None = None) -> tuple[str, str | None]:
    """Run the Planner agent.

    Args:
        user_prompt: The user's request
        resume_session_id: If set, resume a previous planner session

    Returns:
        (result_text, session_id) — session_id can be saved for resume
    """
    SPECS_DIR.mkdir(parents=True, exist_ok=True)

    system_prompt = (PROMPTS_DIR / "planner_system.md").read_text()

    prompt = f"""基于以下需求，为一个个人技术博客生成完整的产品规格。

用户需求：{user_prompt}

你需要：
1. 在 .harness/specs/ 目录下为每个功能模块创建一个 .md 规格文件（如 .harness/specs/homepage.md 等）
2. 在项目根目录创建 fix_plan.md（注意：是根目录，不是 .harness/ 下）— 按优先级排列的实现计划，每项一行，格式为 `- [ ] 功能描述`
3. 在项目根目录创建 AGENT.md（注意：是根目录，不是 .harness/ 下）— 项目构建和运行指南

技术栈约束：Next.js 14+ (App Router) + MDX + CSS Modules + @chenglou/pretext + Framer Motion
功能范围：核心博客功能（文章、分类、标签、搜索、归档）+ 高级UI/UX（暗色模式、动画、响应式）

要求：
- 规格要有野心但务实，聚焦产品上下文和高层技术设计
- 不要过度指定实现细节（让 Generator 自己决定路径）
- 每个 spec 文件包含：功能描述、用户故事、验收标准、设计要求
- 涉及文字排版的 spec 必须标注使用哪个 Pretext API
- fix_plan.md 中的项目按依赖关系排序（基础设施优先）

严格禁止：
- 不要修改任何源码文件（.tsx/.ts/.css/.json 等），你只能写 specs/*.md、fix_plan.md 和 AGENT.md
- 不要运行 npm install、npm run build 等构建命令
- 你的职责是分析和规划，代码实现由 Generator 完成
"""

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=system_prompt,
        allowed_tools=["Read", "Write", "Glob", "Grep", "WebSearch", "WebFetch"],
        permission_mode="bypassPermissions",
        cwd=str(WORKSPACE_DIR),
        max_turns=MAX_PLANNER_TURNS,
        resume=resume_session_id,
    )

    result = ""
    session_id = None

    async with ClaudeSDKClient(options=options) as client:
        # If resuming, send a continue prompt; otherwise send the full prompt
        if resume_session_id:
            _log("Planner", C_CYAN, f"Resuming session {resume_session_id}")
            await client.query("请继续之前的工作。检查 specs/ 和 fix_plan.md，完成剩余的规格编写。")
        else:
            await client.query(prompt)

        while True:
            got_result = False
            needs_followup = False
            followup_answer = None

            async for message in client.receive_response():
                # Capture session_id from init message
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    session_id = message.data.get("session_id")
                    if session_id:
                        _log("Planner", C_DIM, f"session={session_id}")

                # Intercept AskUserQuestion
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock) and block.name == "AskUserQuestion":
                            _log("Planner", C_CYAN, "Asking you a question...")
                            followup_answer = _prompt_user_question(block.input)
                            _log("Answer", C_GREEN, followup_answer)
                            needs_followup = True

                _log_message(message)

                if isinstance(message, ResultMessage):
                    result = message.result or ""
                    if not session_id and hasattr(message, "session_id"):
                        session_id = message.session_id
                    got_result = True

            if needs_followup and followup_answer and not got_result:
                await client.query(followup_answer)
                continue

            break

    return result, session_id
