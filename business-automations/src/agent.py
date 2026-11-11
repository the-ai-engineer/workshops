"""The agent loop: the model picks a tool, the code runs it, repeat until the model answers.

That is all an agent is. The limits are in code, not in the prompt: the agent
can only call the tools it is given, and it stops after max_turns.
"""
from google.genai import types

import tools as toolbox


def run_agent(instruction: str, task: str, tools: list, max_turns: int = 8) -> str:
    """Run the loop and return the agent's final answer. `tools` are plain Python functions."""
    by_name = {tool.__name__: tool for tool in tools}
    config = types.GenerateContentConfig(
        system_instruction=instruction,
        tools=tools,  # the SDK reads each function's name, arguments and docstring
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),  # we run the loop ourselves
    )
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=task)])]
    tokens = 0

    for turn in range(1, max_turns + 1):
        response = toolbox.gemini().models.generate_content(model=toolbox.MODEL, contents=contents, config=config)
        tokens += response.usage_metadata.total_token_count or 0
        if not response.function_calls:  # no tool wanted: this is the answer
            print(f"  agent: {turn} turns, {tokens} tokens")
            return response.text

        contents.append(response.candidates[0].content)
        results = []
        for call in response.function_calls:
            print(f"  tool: {call.name}({', '.join(call.args)})")
            try:
                result = by_name[call.name](**call.args)
            except Exception as error:  # tell the agent, so it can try something else
                result = f"Error: {error}"
            results.append(types.Part(function_response=types.FunctionResponse(
                id=call.id, name=call.name, response={"result": result})))
        contents.append(types.Content(role="user", parts=results))

    raise RuntimeError(f"the agent did not finish in {max_turns} turns")
