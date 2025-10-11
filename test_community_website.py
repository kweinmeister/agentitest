import allure
import pytest

from conftest import BaseAgentTest, BrowserSession, ChatGoogle


@allure.feature("Main Navigation")
class TestMainNavigation(BaseAgentTest):
    """Tests the main navigation links on the home page."""

    @allure.story("Main Navigation Links")
    @allure.title("Test Navigation to {link_text}")
    @pytest.mark.parametrize(
        ("link_text", "expected_path_segment"),
        [
            ("Google Cloud", "/c/google-cloud/14"),
            ("Looker", "/c/looker/19"),
            ("Google Workspace Developers", "/c/google-workspace/20"),
            ("AppSheet", "/c/appsheet/21"),
        ],
    )
    async def test_main_navigation(
        self,
        llm: ChatGoogle,
        browser_session: BrowserSession,
        link_text: str,
        expected_path_segment: str,
    ) -> None:
        """Tests navigation to main sections of the website."""
        task: str = f"click on the '{link_text}' link in the main navigation, and then return the final URL of the page."
        await self.validate_task(llm, browser_session, task, expected_path_segment)


@allure.feature("Home Page Content")
class TestHomePageContent(BaseAgentTest):
    """Tests the visibility of key elements on the home page."""

    EXPECTED_ELEMENTS_VISIBLE = "all_elements_visible"

    @allure.story("Key Element Visibility")
    @allure.title("Test Visibility of Welcome Heading and CTA Buttons")
    async def test_welcome_elements_are_visible(
        self,
        llm: ChatGoogle,
        browser_session: BrowserSession,
    ) -> None:
        """Tests that the main welcome heading and CTA buttons are visible."""
        task: str = f"confirm that the 'Google Developer Program forums' heading is visible on the page. Return '{self.EXPECTED_ELEMENTS_VISIBLE}' if it is."
        await self.validate_task(
            llm,
            browser_session,
            task,
            self.EXPECTED_ELEMENTS_VISIBLE,
            ignore_case=True,
        )


@allure.feature("Search Functionality")
class TestSearch(BaseAgentTest):
    """Tests for the website's search functionality."""

    EXPECTED_NO_RESULTS = "no_results_found"

    @allure.story("Searching for Terms")
    @allure.title("Search for '{term}'")
    @pytest.mark.parametrize("term", ["Google Cloud", "Looker"])
    async def test_search_for_term(
        self,
        llm: ChatGoogle,
        browser_session: BrowserSession,
        term: str,
    ) -> None:
        """Tests searching for a term and verifying results are shown."""
        # The agent can be inefficient. This prompt guides it to the most reliable search method.
        task: str = f"click the search icon, then type '{term}' into the search bar that appears, and then press Enter. Finally, wait for the page to load and confirm that text containing 'results for {term}' is visible. If it is, return 'search_results_visible'."
        expected_confirmation: str = "search_results_visible"
        await self.validate_task(
            llm,
            browser_session,
            task,
            expected_confirmation,
            ignore_case=True,
        )

    @allure.story("Searching for Non-Existent Term")
    @allure.title("Search for a Non-Existent Term")
    async def test_search_for_non_existent_term(
        self,
        llm: ChatGoogle,
        browser_session: BrowserSession,
    ) -> None:
        """Tests searching for a term that should not have results."""
        term: str = "a_very_unlikely_search_term_xyz"
        task: str = f"click the search icon, then type '{term}' into the search bar that appears, and then press Enter. Finally, confirm that a 'no results' message is displayed. If it is, return '{self.EXPECTED_NO_RESULTS}'."
        await self.validate_task(
            llm,
            browser_session,
            task,
            self.EXPECTED_NO_RESULTS,
            ignore_case=True,
        )
