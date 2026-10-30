import pytest
from playwright.async_api import Page, expect
from elements.url_dashboard import url_dashboard


class Page404:
    def __init__(self, page: Page):
        self.page = page


    async def access_view_subuser_list(self):
        await self.page.goto(url_dashboard.VIEW_SUBUSER_LIST)