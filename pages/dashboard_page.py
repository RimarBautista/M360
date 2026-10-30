from playwright.async_api import Page, expect
from elements.dashboard_page_elements import DashboardElements


class DashboardPage:

    def __init__(self, page: Page):
        self.page = page

        self.dashboard = page.locator(DashboardElements.DASHBOARD)
    

    async def assert_dashboard_page(self):
        await expect(self.dashboard).to_be_visible()
