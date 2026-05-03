# Backend Plan

## Goal

Build the backend prompt flow so the task pipeline is clear and each prompt script has one job.

## Prompt Flow

1. `secondPrompt.py`
	Make the text instruction.
	Inputs: schematic image, user image, context text, task status text, and any user input text.
	Output: the text response that explains what should be done.

2. `thirdPrompt.py`
	Convert the text instruction into speech.
	Input: text returned from `secondPrompt.py`.
	Output: audio file path and audio mime type.

3. `fourthPrompt.py`
	Update the current task state in a plain text file.
	Input: task name and the updated task-status text.
	Output: updated `taskStates/taskN/text1.txt` file and returned backend state.

## Task State Format

- Task state is stored in `taskStates/taskN/text1.txt`.
- The file content is plain text.
- This text is the current thing that still needs to be done for the task.
- `fourthPrompt.py` is responsible for writing updates to this file.

## Status

- `secondPrompt.py`: planned first text-generation step
- `thirdPrompt.py`: text-to-speech step
- `fourthPrompt.py`: task-state `.txt` updater
- `backend/AIBackend.py`: coordinator for the prompt flow

## Notes

- Keep task status as readable text, not Python code.
- Keep the prompt flow simple: text first, then speech, then state update.
