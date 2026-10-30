from playwright.async_api import Page
from elements.login_page_elements import LoginElements


class LoginPage:

    def __init__(self, page: Page):
        self.page = page

        self.username = page.locator(LoginElements.USERNAME)
        self.password = page.locator(LoginElements.PASSWORD)
        self.login_button = page.locator(LoginElements.LOGIN_BUTTON)

    async def login(self, username: str, password: str):
        await self.username.fill(username)
        await self.password.fill(password)
        await self.login_button.click()