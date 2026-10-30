import pytest
from pages.dashboard_page import DashboardPage
from pages.page_404 import Page404


@pytest.mark.asyncio
async def test_tc1_access_subuser_list(logged_in_page):

    dashboard = DashboardPage(logged_in_page)
    error404 = Page404(logged_in_page)
    
    await dashboard.assert_dashboard_page()

    await error404.access_view_subuser_list()


    