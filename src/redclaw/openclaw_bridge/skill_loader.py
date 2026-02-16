"""
SkillLoader — Registers RedClaw pentesting skills with OpenClaw's skill platform.

OpenClaw skills are defined in directories with a SKILL.md manifest file.
Each skill describes a set of capabilities the agent can invoke.
This loader reads skill manifests and registers them with the OpenClaw runtime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("redclaw.openclaw_bridge.skill_loader")


@dataclass
class SkillManifest:
    """Parsed skill manifest from SKILL.md frontmatter."""
    name: str
    description: str
    phase: str  # which pipeline phase this skill belongs to
    tools: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    priority: int = 0
    requires_approval: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadedSkill:
    """A fully loaded and registered skill."""
    manifest: SkillManifest
    path: Path
    content: str  # full SKILL.md content (instructions for the agent)
    registered: bool = False


class SkillLoader:
    """
    Discovers, loads, and registers RedClaw pentesting skills.

    Skills directory structure:
      skills/
        recon/
          SKILL.md           # Manifest + instructions
        scanning/
          SKILL.md
        exploitation/
          SKILL.md
        post_exploitation/
          SKILL.md
        reporting/
          SKILL.md

    SKILL.md format:
      ---
      name: recon
      description: Reconnaissance and OSINT gathering
      phase: reconnaissance
      tools: [nmap, masscan]
      triggers: ["scan", "recon", "enumerate"]
      ---
      # Reconnaissance Skill
      Instructions for how to perform reconnaissance...

    Usage:
        loader = SkillLoader("./src/redclaw/skills")
        skills = loader.discover()
        for skill in skills:
            print(f"{skill.manifest.name}: {skill.manifest.description}")
    """

    def __init__(self, skills_dir: str | Path):
        self._skills_dir = Path(skills_dir)
        self._skills: dict[str, LoadedSkill] = {}
        logger.info(f"SkillLoader initialized: dir={self._skills_dir}")

    @property
    def skills(self) -> dict[str, LoadedSkill]:
        return self._skills

    def discover(self) -> list[LoadedSkill]:
        """
        Discover all skills in the skills directory.
        Returns list of loaded skills with parsed manifests.
        """
        if not self._skills_dir.exists():
            logger.warning(f"Skills directory not found: {self._skills_dir}")
            return []

        discovered: list[LoadedSkill] = []

        for skill_dir in sorted(self._skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            manifest_path = skill_dir / "SKILL.md"
            if not manifest_path.exists():
                logger.debug(f"No SKILL.md in {skill_dir.name}, skipping")
                continue

            try:
                skill = self._load_skill(manifest_path)
                self._skills[skill.manifest.name] = skill
                discovered.append(skill)
                logger.info(
                    f"Discovered skill: {skill.manifest.name} "
                    f"(phase={skill.manifest.phase}, tools={skill.manifest.tools})"
                )
            except Exception as e:
                logger.error(f"Failed to load skill from {manifest_path}: {e}")

        logger.info(f"Discovered {len(discovered)} skills")
        return discovered

    def _load_skill(self, manifest_path: Path) -> LoadedSkill:
        """Load and parse a single skill manifest."""
        content = manifest_path.read_text(encoding="utf-8")

        # Parse YAML frontmatter
        frontmatter, body = self._parse_frontmatter(content)

        manifest = SkillManifest(
            name=frontmatter.get("name", manifest_path.parent.name),
            description=frontmatter.get("description", ""),
            phase=frontmatter.get("phase", ""),
            tools=frontmatter.get("tools", []),
            triggers=frontmatter.get("triggers", []),
            priority=frontmatter.get("priority", 0),
            requires_approval=frontmatter.get("requires_approval", False),
            metadata=frontmatter,
        )

        return LoadedSkill(
            manifest=manifest,
            path=manifest_path.parent,
            content=content,
        )

    def _parse_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        """Parse YAML frontmatter from a markdown document."""
        if not content.startswith("---"):
            return {}, content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content

        try:
            frontmatter = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            frontmatter = {}

        body = parts[2].strip()
        return frontmatter, body

    def get_skill(self, name: str) -> Optional[LoadedSkill]:
        """Get a specific skill by name."""
        return self._skills.get(name)

    def get_skills_for_phase(self, phase: str) -> list[LoadedSkill]:
        """Get all skills relevant to a specific pipeline phase."""
        return [s for s in self._skills.values() if s.manifest.phase == phase]

    def get_skill_by_trigger(self, trigger: str) -> Optional[LoadedSkill]:
        """Find a skill that matches a trigger keyword."""
        trigger_lower = trigger.lower()
        for skill in self._skills.values():
            if trigger_lower in [t.lower() for t in skill.manifest.triggers]:
                return skill
        return None

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """
        Generate OpenClaw-compatible tool definitions from all loaded skills.
        These are registered with the OpenClaw agent's tool registry.
        """
        definitions: list[dict[str, Any]] = []

        for skill in self._skills.values():
            for tool_name in skill.manifest.tools:
                definitions.append({
                    "name": f"redclaw_{tool_name}",
                    "description": f"{skill.manifest.description} — {tool_name} tool",
                    "skill": skill.manifest.name,
                    "phase": skill.manifest.phase,
                    "requires_approval": skill.manifest.requires_approval,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": f"Command or parameters for {tool_name}",
                            },
                            "target": {
                                "type": "string",
                                "description": "Target IP, hostname, or URL",
                            },
                            "options": {
                                "type": "object",
                                "description": "Additional tool-specific options",
                            },
                        },
                        "required": ["command"],
                    },
                })

        return definitions

    def __repr__(self) -> str:
        return f"SkillLoader(dir={self._skills_dir}, skills={len(self._skills)})"
