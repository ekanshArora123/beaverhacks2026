"""
Takes context and user update
"""

import importlib.util
from pathlib import Path


TASK_STATES_DIR = Path(__file__).resolve().parent.parent / "taskStates"
TASK_IMAGE_SUFFIXES = {
	".jpg",
	".jpeg",
	".png",
	".webp",
	".gif",
}


class StateUpdateMixin:
	def update_text_source_1(self, new_text_source_1: str) -> dict[str, str | int | list[str] | None]:
		self.text_source_1 = new_text_source_1.strip()
		return self.get_state()

	def get_state(self) -> dict[str, str | int | list[str] | None]:
		return {
			"text_model": self.text_model,
			"vision_model": self.vision_model,
			"voice_model": self.voice_model,
			"selected_model": self.selected_model or None,
			"prompt_number": self.prompt_number,
			"prompt_text": self.prompt_text,
			"image_paths": [str(image_path) for image_path in self.image_paths],
			"task_image_paths": [str(image_path) for image_path in self.task_image_paths],
			"text_source_1": self.text_source_1,
			"text_source_2": self.text_source_2,
			"task_name": self.task_name,
			"task_status": self.task_status or None,
		}

	def _normalize_task_name(self, task_name: str | int | None) -> str | None:
		if task_name is None:
			return None
		if isinstance(task_name, int):
			return f"task{task_name}"

		normalized_name = str(task_name).strip()
		if not normalized_name:
			return None
		if normalized_name.isdigit():
			return f"task{normalized_name}"
		return normalized_name

	def _load_task_status(self, task_name: str) -> str:
		status_path = self.task_states_dir / task_name / "text1.py"
		if not status_path.exists():
			return ""

		spec = importlib.util.spec_from_file_location(f"{task_name}_status_module", status_path)
		if spec is None or spec.loader is None:
			raise RuntimeError(f"Could not load task status from {status_path}.")

		status_module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(status_module)
		status_value = getattr(status_module, "STATUS", "")
		if not isinstance(status_value, str):
			raise ValueError(f"STATUS in {status_path} must be a string.")
		return status_value.strip()

	def _load_task_image_paths(self, task_name: str) -> list[Path]:
		task_dir = self.task_states_dir / task_name
		if not task_dir.exists():
			return []

		return sorted(
			path for path in task_dir.iterdir() if path.is_file() and path.suffix.lower() in TASK_IMAGE_SUFFIXES
		)
