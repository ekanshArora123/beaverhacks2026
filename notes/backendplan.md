# Backend Plan

## Goal

Build the backend prompt flow so the task pipeline is clear and each prompt script has one job.

## Main files:
- `backend/AIBackend.py`: orchestrates prompts 1 -> 2 -> 3 -> 4
- `backend/ApiScripts/`: folder of all prompt scripts

## Prompt Flow

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
