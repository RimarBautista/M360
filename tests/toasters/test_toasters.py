import pytest
from pages.dashboard_page import DashboardPage
from pages.contacts_page import ContactsPage


@pytest.mark.asyncio
async def test_tc1_contacts_creation(logged_in_page):

    dashboard = DashboardPage(logged_in_page)
    contacts_page= ContactsPage(logged_in_page)
    
    await dashboard.assert_dashboard_page()

    await contacts_page.open_contact_list()

    await contacts_page.create_new_contact()


@pytest.mark.asyncio
async def test_tc2_contacts_creation(logged_in_page):

    dashboard = DashboardPage(logged_in_page)
    contacts_page= ContactsPage(logged_in_page)
    
    await dashboard.assert_dashboard_page()

    await contacts_page.open_contact_list()

    await contacts_page.update_contact()

    # Pauses execution for 5 seconds (5000 ms)
    await logged_in_page.wait_for_timeout(5000)
    


    


    