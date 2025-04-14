import json
from openai import OpenAI

class LlmAgent:
    def __init__(self, model="gpt-4"):
        self.client = OpenAI()
        self.model = model

    def diagnose_pod(self, metadata: dict):
        """
        Given a dictionary 'metadata' which might include:
        - "containers": [
            {
                "name": str,
                "image": str,
                "image_valid": bool,    # if you do Docker checks
                "env": [ { "name": ..., "value": ... }, ... ]
            },
            ...
            ]
        - "events": [str, ...]
        - "raw_describe": str
        - Possibly other fields you add

        We pass it all to the LLM. A single conversation:
        1) System message: "Here's how to interpret each field..."
        2) Assistant message: "Here is the metadata: ... (the JSON dump)."
        3) User message: "Given this data, what's the likely root cause & fix?"

        The LLM can handle many potential issues (image invalid, environment problems, CrashLoopBackOff, etc.)
        """

        # 1) Summarise or define the meaning of each field for the LLM in the system prompt
        #    This ensures it knows how to interpret, e.g. "image_valid: false => the image might be missing."
        system_prompt = (
            "You are an AI diagnosing K8s pods. We have some metadata fields:\n"
            "- 'containers': a list of containers in this pod.\n"
            "   Each container can have:\n"
            "      name: container name.\n"
            "      image: the Docker image string.\n"
            "      image_valid: a boolean we derived from checking if the image exists in a registry.\n"
            "         (true means we verified the image can be pulled, false means it's likely invalid or private.)\n"
            "      env: environment variables in that container.\n"
            "- 'events': lines from 'kubectl describe' that show warnings or error messages.\n"
            "- 'raw_describe': the entire text from 'kubectl describe pod'.\n"
            "If 'image_valid' is false, it might indicate an invalid or non-existent container image.\n"
            "If 'events' mention CrashLoopBackOff, or ErrImagePull, that's also relevant.\n"
            "Use these clues to figure out potential root causes.\n"
            "Finally, propose recommended fixes or next steps.\n"
        )

        # 2) Turn your metadata into a JSON string. That can be 'assistant' role,
        #    so the LLM sees it as data it can parse or read.
        metadata_json = json.dumps(metadata, indent=2)

        # 3) We'll define a user prompt that instructs the LLM to provide a diagnosis
        user_prompt = (
            "Given the above metadata, please diagnose the likely cause(s) of any issues. "
            "Propose how to fix them or what next steps to take. If everything looks fine, say so."
        )

        # Build the conversation
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "assistant",
                "content": f"Here is the metadata:\n{metadata_json}"
            },
            {"role": "user", "content": user_prompt}
        ]
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content

