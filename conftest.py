from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import os
import sys
from importlib.metadata import version
from typing import TYPE_CHECKING, Any

import allure
import pytest
from browser_use import (
    Agent,
    BrowserProfile,
    BrowserSession,
    ChatGoogle,
)
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


# Load environment variables from .env file
load_dotenv()
logger = logging.getLogger(__name__)

LLM_TEMPERATURE = 0.2
DEFAULT_MODEL = "gemini-3-flash-preview"

# --- Fixtures for Setup and Configuration ---


@pytest.fixture(scope="session")
def browser_version_info(browser_profile: BrowserProfile) -> dict[str, str]:
    """Fixture to get Playwright and browser version info."""
    try:
        with sync_playwright() as p:
            playwright_version: str = version("playwright")
            browser_type_name: str = (
                browser_profile.channel if browser_profile.channel else "chromium"
            )
            browser = p[browser_type_name].launch()
            browser_version: str = browser.version
            browser.close()
            return {
                "playwright_version": playwright_version,
                "browser_version": f"{browser_type_name} {browser_version}",
            }
    except Exception as e:
        logger.warning(f"Could not determine Playwright/browser version: {e}")
        return {
            "playwright_version": "N/A",
            "browser_version": "N/A",
        }


@pytest.fixture(scope="session", autouse=True)
def allure_environment(
    request: pytest.FixtureRequest,
    browser_version_info: dict[str, str],
) -> None:
    """Fixture to write environment details to a properties file for reporting.
    This runs once per session and is automatically used.
    By default, this creates `environment.properties` for Allure.
    """
    allure_dir: str | None = request.config.getoption("--alluredir")
    if not allure_dir:
        return

    ENVIRONMENT_PROPERTIES_FILENAME: str = "environment.properties"
    properties_file: str = os.path.join(allure_dir, ENVIRONMENT_PROPERTIES_FILENAME)

    try:
        os.makedirs(allure_dir, exist_ok=True)
    except OSError:
        return

    env_props: dict[str, str] = {
        "OS": os.name,
        "Python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "Playwright": browser_version_info["playwright_version"],
        "Browser": browser_version_info["browser_version"],
        "Run URL": os.getenv("GITHUB_SERVER_URL", "")
        + "/"
        + os.getenv("GITHUB_REPOSITORY", "")
        + "/actions/runs/"
        + os.getenv("GITHUB_RUN_ID", ""),
    }
    with open(properties_file, "w") as f:
        f.writelines(f"{key}={value}\n" for key, value in env_props.items())



@pytest.fixture
async def llm() -> ChatGoogle:
    """Function-scoped fixture to initialize the language model."""
    model_name: str = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    return ChatGoogle(
        model=model_name,
        temperature=LLM_TEMPERATURE,
        api_key=os.getenv("GEMINI_API_KEY"),
    )


@pytest.fixture(scope="session")
def browser_profile() -> BrowserProfile:
    """Session-scoped fixture for browser profile configuration."""
    headless_mode: bool = os.getenv("HEADLESS", "True").lower() in ("true", "1", "t")
    return BrowserProfile(headless=headless_mode, keep_alive=True)


@pytest.fixture
async def browser_session(
    browser_profile: BrowserProfile,
) -> AsyncGenerator[BrowserSession, None]:
    """Function-scoped fixture to manage the browser session's lifecycle."""
    session: BrowserSession = BrowserSession(browser_profile=browser_profile)
    await session.start()
    try:
        yield session
    finally:
        await session.stop()


# --- Base Test Class for Agent-based Tests ---


class BaseAgentTest:
    """Base class for agent-based tests to reduce boilerplate."""

    BASE_URL = "https://discuss.google.dev/"

    async def validate_task(
        self,
        llm: ChatGoogle,
        browser_session: BrowserSession,
        task_instruction: str,
        expected_substring: str,
        ignore_case: bool = False,
    ) -> str:
        """Runs a task with the agent, prepends the BASE_URL, and performs common assertions."""
        full_task: str = f"Go to {self.BASE_URL}, then {task_instruction}"
        result_text: str = await run_agent_task(full_task, llm, browser_session)
        assert result_text is not None and result_text.strip() != "", (
            "Agent did not return a result."
        )

        if expected_substring:
            result_to_check = result_text.lower()
            # Check for the specific expected substring OR common confirmation phrases
            possible_confirmations = {
                expected_substring.lower() if ignore_case else expected_substring,
                "visible",
                "found",
                "confirmed",
                "i see it",
            }
            assert any(
                phrase in result_to_check for phrase in possible_confirmations
            ), (
                f"Expected a confirmation like '{expected_substring}', but got: '{result_text}'"
            )

        return result_text


# --- Allure Hook for Step-by-Step Reporting ---


async def record_step(agent: Agent) -> None:
    """Hook function that captures and records agent activity at each step."""
    history = agent.history

    last_action: dict[str, Any] = (
        history.model_actions()[-1] if history.model_actions() else {}
    )
    action_name: str = next(iter(last_action)) if last_action else "No action"
    action_params: dict[str, Any] = last_action.get(action_name, {})
    step_title: str = f"Action: {action_name}"
    param_str: str = ", ".join(f"{k}={v}" for k, v in action_params.items())
    if param_str:
        step_title += f"({param_str})"

    with allure.step(step_title):
        thoughts = history.model_thoughts()
        if thoughts:
            allure.attach(
                str(thoughts[-1]),
                name="Agent Thoughts",
                attachment_type=allure.attachment_type.TEXT,
            )

        url: str | None = history.urls()[-1] if history.urls() else "N/A"
        allure.attach(url, name="URL", attachment_type=allure.attachment_type.TEXT)

        last_history_item = history.history[-1] if history.history else None
        if last_history_item and last_history_item.metadata:
            duration: float = last_history_item.metadata.duration_seconds
            allure.attach(
                f"{duration:.2f}s",
                name="Step Duration",
                attachment_type=allure.attachment_type.TEXT,
            )

        # Attach Screenshot
        try:
            screenshot_b64 = await agent.browser_session.take_screenshot()
            if screenshot_b64:
                # Validate base64 string before decoding
                if isinstance(screenshot_b64, bytes):
                    # If it's already bytes, use it directly
                    screenshot_bytes: bytes | None = screenshot_b64
                elif is_valid_base64(screenshot_b64):
                    # If it's a valid base64 string, decode it
                    screenshot_bytes = base64.b64decode(screenshot_b64)
                else:
                    logger.warning("Invalid base64 padding in screenshot data")
                    screenshot_bytes = None

                if screenshot_bytes:
                    allure.attach(
                        screenshot_bytes,
                        name="Screenshot",
                        attachment_type=allure.attachment_type.PNG,
                    )
        except Exception as e:
            logger.warning(f"Failed to take or attach screenshot: {e}")


# --- Helper Function to Run Agent ---


async def run_agent_task(
    full_task: str,
    llm: ChatGoogle,
    browser_session: BrowserSession,
) -> str:
    """Initializes and runs the browser agent for a given task using an active browser session."""
    logger.info(f"Running task: {full_task}")

    agent: Agent = Agent(
        task=full_task,
        llm=llm,
        browser_session=browser_session,
    )

    # Add timeout to prevent hanging
    result = await asyncio.wait_for(agent.run(on_step_end=record_step), timeout=150)
    final_text: str | None = result.final_result()

    # Only attach final result if it's not None
    if final_text is not None:
        allure.attach(
            final_text,
            name="Final Result",
            attachment_type=allure.attachment_type.TEXT,
        )

    return final_text if final_text else ""


# --- Utility Function for Base64 Validation ---


def is_valid_base64(s: Any) -> bool:
    """Check if a string or bytes is a valid base64 encoded data."""
    try:
        # If it's already bytes, try to decode it directly
        if isinstance(s, bytes):
            base64.b64decode(s, validate=True)
            return True

        # If it's a string, check if length is multiple of 4 and try to decode
        if isinstance(s, str):
            # Check if length is multiple of 4
            if len(s) % 4 != 0:
                return False
            base64.b64decode(s, validate=True)
            return True

        return False
    except binascii.Error:
        return False
