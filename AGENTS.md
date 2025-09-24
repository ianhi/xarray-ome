# Agent Instructions

## Project Context

**ALWAYS read `plan.md` first** to understand the project's goals, architecture decisions, and implementation approach before making any code changes.

## Code Style Guidelines

### Follow Idiomatic Python Best Practices

- Use pythonic patterns and conventions
- Follow PEP 8 style guidelines (enforced by ruff)
- Write clear, readable code that speaks for itself
- Use meaningful variable and function names
- Follow established patterns in the existing codebase

### Comments Policy

**DO NOT leave excessive comments in code.**

- Write self-documenting code with clear names and structure
- Only add comments when absolutely necessary to explain complex logic or non-obvious decisions
- Prefer docstrings for functions/classes over inline comments
- Trust that the code itself tells the story

### Code Quality Standards

- All code must pass pre-commit hooks (ruff, mypy, etc.)
- Follow the existing project structure and patterns
- Use type hints appropriately
- Write tests for new functionality
- Keep functions and classes focused and single-purpose

## Development Workflow

1. Read `plan.md` to understand context
2. Check existing code patterns before implementing
3. Write clean, self-documenting code
4. Ensure all linting and type checking passes
<!-- 5. Run tests to verify functionality -->
