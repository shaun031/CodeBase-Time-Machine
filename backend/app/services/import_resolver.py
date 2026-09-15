from pathlib import PurePosixPath
from uuid import UUID


class ImportResolver:
    EXTENSIONS = (
        ".py",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".java",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".hpp",
        ".go",
        ".php",
    )

    @staticmethod
    def _normalize(path: PurePosixPath) -> str | None:
        parts: list[str] = []
        for part in path.parts:
            if part in {"", "."}:
                continue
            if part == "..":
                if not parts:
                    return None
                parts.pop()
            else:
                parts.append(part)
        return "/".join(parts)

    def resolve(
        self, source_path: str, module: str, language: str | None, files: dict[str, UUID]
    ) -> UUID | None:
        source = PurePosixPath(source_path)
        candidates: list[str] = []
        if language == "Python":
            dots = len(module) - len(module.lstrip("."))
            remainder = module[dots:].replace(".", "/")
            base = source.parent
            for _ in range(max(0, dots - 1)):
                base = base.parent
            value = self._normalize(base / remainder) if dots else module.replace(".", "/")
            if value:
                candidates.extend([f"{value}.py", f"{value}/__init__.py"])
        elif module.startswith("."):
            value = self._normalize(source.parent / module)
            if value:
                candidates.extend(
                    [
                        value,
                        *(f"{value}{ext}" for ext in self.EXTENSIONS),
                        *(f"{value}/index{ext}" for ext in self.EXTENSIONS),
                    ]
                )
        elif language in {"C", "C++"}:
            value = self._normalize(source.parent / module)
            if value:
                candidates.extend([value, module])
        elif language in {"Java", "PHP"}:
            value = module.replace("\\", "/").replace(".", "/").removesuffix("/*")
            candidates.extend(f"{value}{ext}" for ext in (".java", ".php"))
        for candidate in candidates:
            target = files.get(candidate)
            if target is not None:
                return target
        return None
