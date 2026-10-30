from playwright.async_api import Page, expect
from elements.reports_page_elements import ReportsPageElements


class ReportsPage:

    def __init__(self, page: Page):
        self.page = page

        self.reports = page.locator(ReportsPageElements.REPORTS)
        self.channel_reports = page.locator(ReportsPageElements.CHANNEL_REPORTS)
        self.service_reports = page.locator(ReportsPageElements.SERVICE_REPORTS)
        self.opt_out_reports = page.locator(ReportsPageElements.OPTOUT_REPORTS)
        self.click_tracking_reports = page.locator(ReportsPageElements.CLICK_TRACKING_REPORTS)

    async def assert_reports_page(self):
        await expect(self.reports).to_be_visible()

    #Channel Reports function
    async def open_channel_reports(self):
        await self.channel_reports.click()

    async def assert_channel_reports_page(self):
        await expect(self.page).to_have_url(
            "https://stg-portal.m360.com.ph/reports/channel/overview"
        )
