# Backend Plan

## Goal
Build the backend prompt flow so the task pipeline is clear and each prompt script has one job.

## Main files:
- `backend/programAPI.py`: API entrypoint that handles request parsing and voice transcription before prompt execution
- `backend/AIBackend.py`: orchestrates the four prompt methods (`run_first_prompt` -> `run_second_prompt` -> `run_third_prompt` -> `run_fourth_prompt`)
- `backend/ApiScripts/`: folder of all prompt scripts
- `backend/ApiScripts/GeminiEndpoint/config.py`: models config

## Prompt Flow

Note: The pipeline has 5 stages total. Stage 1 is voice transcription. Stages 2-5 are the four prompt methods in `AIBackend.py`.

1. `voiceToText.py`
	Convert the user's speech to text.
	Input: user's speech.
	Output: user text.

2. `mainPrompt.py`
	Make the text instruction (`run_first_prompt`).
	Inputs: (schematic image, user image, context text, task status text, user text) = input1
	Output: the text response that explains what should be done.

3. `diagramPrompt.py`
	Create the schematic diagram (`run_second_prompt`).
	Input: input1 + (text returned from `mainPrompt.py`) = input2
	Output: diagram image.

4. `textToSpeech.py`
	Convert the text instruction into speech (`run_third_prompt`).
	Input: text returned from `mainPrompt.py`.
	Output: audio file path and audio mime type.

5. `updatePrompt.py`
	Update the current task state in a plain text file (`run_fourth_prompt`).
	Input: task name and the updated task-status text.
	Output: updated `taskStates/taskN/text1.txt` file and returned backend state.

## Task State Format

- Task state is stored in `taskStates/taskN/text1.txt`.
- The file content is plain text.
- This text is the current thing that still needs to be done for the task.
- `updatePrompt.py` is responsible for writing updates to this file.

## Notes
- Keep task status as readable text, not Python code.
