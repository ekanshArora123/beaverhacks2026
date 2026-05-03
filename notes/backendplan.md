# Backend Plan

## Goal
Keep the prompt pipeline clear, with each prompt script doing one job and the request contract aligned with the current looping frontend behavior.

## Main files:
- `backend/programAPI.py`: API entrypoint that handles request parsing and voice transcription before prompt execution
- `backend/AIBackend.py`: orchestrates the four prompt methods (`run_first_prompt` -> `run_second_prompt` -> `run_third_prompt` -> `run_fourth_prompt`)
- `backend/ApiScripts/`: folder of all prompt scripts
- `backend/ApiScripts/GeminiEndpoint/config.py`: models config
- `frontend/src/App.tsx`: collects media and controls looping-mode image selection before calling `/analyze`

## Prompt Flow

Note: The pipeline has 5 stages total. Stage 1 is voice transcription. Stages 2-5 are the four prompt methods in `AIBackend.py`.

1. `voiceToText.py`
	Convert the user's speech to text.
	Input: user's speech.
	Output: user text.

2. `mainPrompt.py`
	Make the text instruction (`run_first_prompt`).
	Inputs: (schematic image(s), user image(s), context text, task status text, user text) = input1
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

## Image Input Contract

- Backend accepts two image sources on `/analyze`:
	- `image_paths`: workspace file paths resolved by `programAPI.py` (used for schematics/reference images)
	- uploaded file fields (`images`, `image`, `files`, `file`): user-captured images
- Backend combines both sources before prompt execution.
- Schematic images are intentionally sent via `image_paths` so they can be treated separately from user capture selection logic.

## Looping Mode Policy (Current)

- User captures are selected in the frontend before request send:
	- default: include all captured user images
	- fallback when context is getting heavy: include only last `n` user images (`n = 3`)
- Schematic image(s) are always included and are not counted toward `n`.
- Backend stays source-agnostic and processes whatever image set is sent.

## API Notes

- `/analyze` now returns:
	- `text` (assistant response)
	- `model`
	- `user_input_text` (resolved/transcribed user text used for prompt input)
- The frontend uses `user_input_text` to build rolling context across loop iterations.

## Task State Format

- Task state is stored in `taskStates/taskN/text1.txt`.
- The file content is plain text.
- This text is the current thing that still needs to be done for the task.
- `updatePrompt.py` is responsible for writing updates to this file.
- Status writes currently replace the file content (current state), not append historical logs.

## Notes
- Keep task status as readable text, not Python code.
