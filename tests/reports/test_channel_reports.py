import pytest

from pages.reports_page import ReportsPage


@pytest.mark.asyncio
async def test_tc_access_reports_page1(logged_in_page):

    reports = ReportsPage(logged_in_page)

    await reports.assert_reports_page()

@pytest.mark.asyncio
async def test_tc_access_reports_page2(logged_in_page):

    reports = ReportsPage(logged_in_page)

    await reports.assert_reports_page()

@pytest.mark.asyncio
async def test_tc_access_reports_page3(logged_in_page):

    reports = ReportsPage(logged_in_page)

    await reports.assert_reports_page()