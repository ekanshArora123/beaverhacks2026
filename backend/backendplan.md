# Backend Plan

## Goal

Build the backend prompt flow so the task pipeline is clear and each prompt script has one job.

## Main files:
- `backend/AIBackend.py`: TODO
- `backend/promptScripts/`: folder of all prompt scripts
	//Do we want to combine voiceToText and textToSpeech into the same file?

## Prompt Flow

1. `voiceToText.py`
	Convert the user's speech to text.
	Input: user's speech.
	Output: user text.

2. `mainPrompt.py`
	Make the text instruction.
	Inputs: (schematic image, user image, context text, task status text, user text) = input1
	Output: the text response that explains what should be done.

3. `diagramPrompt.py`
	Create the schematic diagram.
	Input: input1 + (text returned from `mainPrompt.py`) = input2
	Output: diagram image.

4. `textToSpeech.py`
	Convert the text instruction into speech.
	Input: text returned from `mainPrompt.py`.
	Output: audio file path and audio mime type.

4. `updatePrompt.py`
	Update the current task state in a plain text file.
	Input: task name and the updated task-status text.
	Output: updated `taskStates/taskN/text1.txt` file and returned backend state.

## Task State Format

- Task state is stored in `taskStates/taskN/text1.txt`.
- The file content is plain text.
- This text is the current thing that still needs to be done for the task.
- `updatePrompt.py` is responsible for writing updates to this file.

## Status

- `mainPrompt.py`: planned first text-generation step
- `textToSpeech.py`: text-to-speech step
- `updatePrompt.py`: task-state `.txt` updater
- `backend/AIBackend.py`: coordinator for the prompt flow

## Notes

- Keep task status as readable text, not Python code.
- Keep the prompt flow simple: text first, then speech, then state update.
