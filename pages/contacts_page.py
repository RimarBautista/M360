from playwright.async_api import Page, expect
from elements.contacts_page_elements import ContactsElements
import random
import string

def generate_unique_first_name():
    letters = string.ascii_lowercase
    random_letters = "".join(random.choice(letters) for _ in range(5))
    return f"TestUser{random_letters}"

def generate_random_ph_number():
    prefixes = ["+63917", "+63918", "+63920", "+63956", "+63995", "+63998"]
    random_prefix = random.choice(prefixes)
    random_digits = random.randint(1000000, 9999999)  # 7 random digits
    return f"{random_prefix}{random_digits}"


class ContactsPage:

    def __init__(self, page: Page):
        self.page = page

        self.contacts = page.locator(ContactsElements.CONTACTS)
        self.contact_list = page.get_by_text(ContactsElements.CONTACT_LIST)
        self.add_new_contact = page.locator(ContactsElements.ADD_NEW_CONTACT_BTN)
        self.fname_txtbox = page.get_by_placeholder(ContactsElements.FIRST_NAME_TXTBOX)
        self.mobile_number_txtbox = page.get_by_placeholder(ContactsElements.MOBILE_NUMBER)
        self.save_btn = page.get_by_text(ContactsElements.SAVE_BUTTON)
        self.toast_message = page.locator(ContactsElements.TOAST_MESSAGE)
        self.select_1st_row = page.locator(ContactsElements.FIRST_ROW_LIST)
        self.contact_edit_button = page.locator(ContactsElements.EDIT_CONTACT)

    async def open_contacts(self):
        await self.contacts.hover()

    async def open_contact_list(self):
        await self.contacts.hover()
        await self.contact_list.click()

        # Force click in case hover overlay is slightly blocking
        await self.contact_list.click(force=True) 

    async def create_new_contact(self):

        # CLICK THE ADD NEW CONTACT BUTTON
        await expect(self.add_new_contact).to_be_visible(timeout=10000)
        await self.add_new_contact.click()


        # ENTER FIRST NAME
        first_name = generate_unique_first_name()
        await expect(self.fname_txtbox).to_be_visible(timeout=10000)
        await self.fname_txtbox.fill(first_name)


        # ENTER MOBILE NUMBER
        mobile_number = generate_random_ph_number()
        await expect(self.fname_txtbox).to_be_visible(timeout=10000)
        await self.mobile_number_txtbox.fill(mobile_number)

        # SAVE BUTTON
        await expect(self.save_btn).to_be_enabled(timeout=10000)
        await self.save_btn.click()

        # ASSERT TOAST
        toast = self.toast_message.first
        await toast.wait_for(state="visible", timeout=5000)
        await expect(toast).to_contain_text(f"{first_name} added successfully.")

    async def update_contact(self):
        #CLICK 1ST CONTACT ON THE LIST
        await self.select_1st_row.first.locator('a').first.click()
        if await self.contact_edit_button.is_visible():
            await self.contact_edit_button.click()
