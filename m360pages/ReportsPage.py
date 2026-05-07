import string
import time

from selenium.webdriver.common.by import By
from m360helper.selenium_helper import SeleniumHelper
from conftest import email


class ReportsPage(SeleniumHelper):
    def __init__(self, driver):
        super().__init__(driver)
        self.alphabet_list = None

    reports_tab_element = (By.XPATH, "//span[text()='Reports']")
    channel_report_card = (By.XPATH, "//a[@href='/reports/channel/overview']")
    SMS_button = (By.XPATH, "//section[@class='reports-channel-section-tab-con']/child::span[contains(text(), 'SMS ')]")
    SMS_tab = (By.XPATH, "// a[ @ href = '/reports/channel/sms']")

    total = (By.XPATH, "//h2")
    SMS_sent = (By.XPATH, "//span[@data-testid='sms-sent-value']")
    SMS_ac = (By.XPATH, "//span[@data-testid='sms-delivered-value']")
    SMS_failed = (By.XPATH, "//span[@data-testid='sms-failed-value']")
    SMS_received = (By.XPATH, "//span[@data-testid='sms-received-value']")
    SMS_overview = (By.XPATH, "//span[text()='SMS Overview']")

    domestic_SMS = (By.XPATH, "//h4[@data-testid='message-type-acknowledged-domestic-sms-value']")
    domestic_SMS_premium_sender_ID = (By.XPATH, "//h4[@data-testid='message-type-acknowledged-domestic-sms-premium-sender-id-value']")
    international_SMS = (By.XPATH, "//h4[@data-testid='message-type-acknowledged-international-sms-value']")
    domestic_SMS_sent = (By.XPATH, "//div[@data-testid='message-type-acknowledged-domestic-sms-sent']")
    domestic_SMS_ack = (By.XPATH, "//span[@data-testid='message-type-acknowledged-domestic-sms-acknowledged']")
    domestic_SMS_failed = (By.XPATH, "//span[@data-testid='message-type-acknowledged-domestic-sms-failed']")
    domestic_SMS_premium_sender_ID_sent = (By.XPATH, "//div[@data-testid='message-type-acknowledged-domestic-sms-premium-sender-id-sent']")
    domestic_SMS_premium_sender_ID_ack = (By.XPATH, "//span[@data-testid='message-type-acknowledged-domestic-sms-premium-sender-id-acknowledged']")
    domestic_SMS_premium_sender_ID_failed = (By.XPATH, "//span[@data-testid='message-type-acknowledged-domestic-sms-premium-sender-id-failed']")
    international_SMS_sent = (By.XPATH, "//div[@data-testid='message-type-acknowledged-international-sms-sent']")
    international_SMS_ack = (By.XPATH, "//span[@data-testid='message-type-acknowledged-international-sms-acknowledged']")
    international_SMS_failed = (By.XPATH, "//span[@data-testid='message-type-acknowledged-international-sms-failed']")

    broadcast_sent = (By.XPATH, "//div[@data-testid='messages-by-service-broadcast-sent']")
    broadcast_ack = (By.XPATH, "//span[@data-testid='messages-by-service-broadcast-acknowledged']")
    broadcast_failed = (By.XPATH, "//span[@data-testid='messages-by-service-broadcast-failed']")
    broadcast_received = (By.XPATH, "//div[@data-testid='messages-by-service-broadcast-received']")

    two_way_message_sent = (By.XPATH, "//div[@data-testid='messages-by-service-two-way-messaging-sent']")
    two_way_message_ack = (By.XPATH, "//span[@data-testid='messages-by-service-two-way-messaging-acknowledged']")
    two_way_message_failed = (By.XPATH, "//span[@data-testid='messages-by-service-two-way-messaging-failed']")
    two_way_message_received = (By.XPATH, "//div[@data-testid='messages-by-service-two-way-messaging-received']")

    SMS_poll_sent = (By.XPATH, "//div[@data-testid='messages-by-service-sms-polls-sent']")
    SMS_poll_ack = (By.XPATH, "//span[@data-testid='messages-by-service-sms-polls-acknowledged']")
    SMS_poll_failed = (By.XPATH, "//span[@data-testid='messages-by-service-sms-polls-failed']")
    SMS_poll_received = (By.XPATH, "//div[@data-testid='messages-by-service-sms-polls-received']")

    api_sent = (By.XPATH, "//div[@data-testid='messages-by-service-api-sent']")
    api_ack = (By.XPATH, "//span[@data-testid='messages-by-service-api-acknowledged']")
    api_failed = (By.XPATH, "//span[@data-testid='messages-by-service-api-failed']")
    api_received = (By.XPATH, "//div[@data-testid='messages-by-service-api-received']")

    def goto_reports(self):
        time.sleep(1)
        self.click_element(self.SMS_tab)

    def goto_report_card(self):
        self.capture_screenshot("Screenshots/Dashboard.png")
        time.sleep(2)
        # self.click_element(self.channel_report_card)
        # self.click_element(self.SMS_button)
        self.scroll_down(100)
        self.capture_screenshot("Screenshots/Report1.png")
        self.scroll_down(800)
        self.capture_screenshot("Screenshots/Report2.png")
        self.scroll_down(1600)
        self.capture_screenshot("Screenshots/Report3.png")
        self.scroll_down(2200)
        self.capture_screenshot("Screenshots/Report4.png")


    def create_xl_report(self):
        self.create_header()
        self.insert_value_in_report(email,self.get_val(self.total),
                                    self.get_val(self.SMS_sent),
                                    self.get_val(self.SMS_ac),
                                    self.get_val(self.SMS_failed),
                                    self.get_val(self.SMS_received),
                                    self.get_val(self.domestic_SMS),
                                    self.get_val(self.domestic_SMS_premium_sender_ID),
                                    self.get_val(self.international_SMS),
                                    self.get_val(self.domestic_SMS_sent),
                                    self.get_val(self.domestic_SMS_ack),
                                    self.get_val(self.domestic_SMS_failed),
                                    self.get_val(self.domestic_SMS_premium_sender_ID_sent),
                                    self.get_val(self.domestic_SMS_premium_sender_ID_ack),
                                    self.get_val(self.domestic_SMS_premium_sender_ID_failed),
                                    self.get_val(self.international_SMS_sent),
                                    self.get_val(self.international_SMS_ack),
                                    self.get_val(self.international_SMS_failed),
                                    self.get_val(self.broadcast_sent),
                                    self.get_val(self.broadcast_ack),
                                    self.get_val(self.broadcast_failed),
                                    self.get_val(self.broadcast_received),
                                    self.get_val(self.two_way_message_sent),
                                    self.get_val(self.two_way_message_ack),
                                    self.get_val(self.two_way_message_failed),
                                    self.get_val(self.two_way_message_received),
                                    self.get_val(self.SMS_poll_sent),
                                    self.get_val(self.SMS_poll_ack),
                                    self.get_val(self.SMS_poll_failed),
                                    self.get_val(self.SMS_poll_received),
                                    self.get_val(self.api_sent),
                                    self.get_val(self.api_ack),
                                    self.get_val(self.api_failed),
                                    self.get_val(self.api_received)

                                    )


    def check_page_element(self):
        return self.web_element_display(self.SMS_overview)