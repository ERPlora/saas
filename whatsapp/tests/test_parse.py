"""WHATSAPP-G07 · Reading Meta's webhook: what each change means for a business, before anything is stored.

Bodies from Meta's reference (https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components and
the Embedded Signup «coexistence» webhooks) and the old product's tests (``test_webhook_echo_ingest.py``,
``test_webhook_history_ingest.py``, ``test_inbox_reply_to.py``, ``test_inbox_reply_id.py``,
``test_delivery_status.py``). The result is the body of the Hub's door 1 (``POST /internal/whatsapp/inbound``)
and door 2 (``/status``) without ``hub`` and the attachment's address, and the verdicts of Meta on templates.
"""

from whatsapp import parse

PHONE_NUMBER_ID = "106540352242922"
BUSINESS = "34910000000"
CUSTOMER = "34600111222"
WABA = "102290129340398"


def webhook(field: str, value: dict, *, waba: str = WABA) -> dict:
    return {"object": "whatsapp_business_account", "entry": [{"id": waba, "changes": [{"field": field, "value": value}]}]}


def messages(*items, contacts=None, **extra) -> dict:
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": BUSINESS, "phone_number_id": PHONE_NUMBER_ID},
        "messages": list(items),
        **extra,
    }
    if contacts is not None:
        value["contacts"] = contacts
    return webhook("messages", value)


def text(wamid="wamid.A", sender=CUSTOMER, body="Hola", **extra) -> dict:
    return {"from": sender, "id": wamid, "timestamp": "1760522400", "type": "text", "text": {"body": body}, **extra}


def only_message(payload) -> parse.Message:
    (message,) = parse.parse(payload).messages
    return message


class TestACustomersMessage:
    def test_a_text_is_door_1s_body(self):
        message = only_message(messages(text(), contacts=[{"profile": {"name": "Ana"}, "wa_id": CUSTOMER}]))

        assert (message.phone_number_id, message.wa_message_id, message.contact) == (PHONE_NUMBER_ID, "wamid.A", CUSTOMER)
        assert message.body == {
            "wa_message_id": "wamid.A",
            "from": CUSTOMER,
            # saas#2670: the profile name Meta sends next to the message reaches the inbox.
            "contact_name": "Ana",
            "direction": "inbound",
            "source": "live",
            "type": "text",
            "text": "Hola",
            "media": None,
            "reply_to": "",
            "reply": None,
            "sent_at": "2025-10-15T10:00:00Z",
            "payload": text(),
        }
        assert message.media_id == ""

    def test_a_photo_carries_its_attachment_and_caption(self):
        photo = {
            "from": CUSTOMER,
            "id": "wamid.P",
            "timestamp": "1760522400",
            "type": "image",
            "image": {"id": "1479537139650973", "mime_type": "image/jpeg", "sha256": "x", "caption": "Mi pelo"},
        }

        message = only_message(messages(photo))

        assert message.media_id == "1479537139650973"
        assert message.body["media"] == {"mime_type": "image/jpeg", "filename": "", "caption": "Mi pelo"}
        assert message.body["text"] == "Mi pelo"

    def test_a_document_carries_its_file_name(self):
        document = {
            "from": CUSTOMER,
            "id": "wamid.D",
            "timestamp": "1760522400",
            "type": "document",
            "document": {"id": "77", "mime_type": "application/pdf", "filename": "factura.pdf"},
        }

        message = only_message(messages(document))

        assert message.body["media"] == {"mime_type": "application/pdf", "filename": "factura.pdf", "caption": ""}

    def test_a_reply_says_which_message_it_answers(self):
        """saas#1919: two questions in a row, the answer says which."""
        message = only_message(messages(text(context={"from": BUSINESS, "id": "wamid.Q2"})))

        assert message.body["reply_to"] == "wamid.Q2"

    def test_a_tapped_template_button_is_its_payload_and_text(self):
        button = {
            "from": CUSTOMER,
            "id": "wamid.B",
            "timestamp": "1760522400",
            "type": "button",
            "context": {"from": BUSINESS, "id": "wamid.T"},
            "button": {"payload": "confirm_yes", "text": "Sí"},
        }

        message = only_message(messages(button))

        assert message.body["reply"] == {"id": "confirm_yes", "title": "Sí"}
        assert (message.body["reply_to"], message.body["text"]) == ("wamid.T", "Sí")

    def test_a_tapped_list_row_is_its_id_and_title(self):
        tapped = {
            "from": CUSTOMER,
            "id": "wamid.L",
            "timestamp": "1760522400",
            "type": "interactive",
            "context": {"id": "wamid.M"},
            "interactive": {"type": "list_reply", "list_reply": {"id": "slot_10", "title": "10:00", "description": ""}},
        }

        message = only_message(messages(tapped))

        assert message.body["reply"] == {"id": "slot_10", "title": "10:00"}
        assert message.body["reply_to"] == "wamid.M"

    def test_a_tapped_reply_button_is_its_id_and_title(self):
        tapped = {
            "from": CUSTOMER,
            "id": "wamid.R",
            "timestamp": "1760522400",
            "type": "interactive",
            "interactive": {"type": "button_reply", "button_reply": {"id": "yes", "title": "Sí"}},
        }

        assert only_message(messages(tapped)).body["reply"] == {"id": "yes", "title": "Sí"}

    def test_a_reaction_is_its_emoji_on_the_message_it_answers(self):
        reaction = {
            "from": CUSTOMER,
            "id": "wamid.X",
            "timestamp": "1760522400",
            "type": "reaction",
            "reaction": {"message_id": "wamid.T", "emoji": "👍"},
        }

        message = only_message(messages(reaction))

        assert (message.body["type"], message.body["text"], message.body["reply_to"]) == ("reaction", "👍", "wamid.T")

    def test_a_message_without_id_or_sender_is_skipped(self):
        parsed = parse.parse(messages({"id": "wamid.N", "type": "text"}, {"from": CUSTOMER, "type": "text"}))

        assert parsed.messages == []
        assert parsed.skipped == 2


class TestTheOwnersReplyFromThePhone:
    def test_an_echo_is_the_business_speaking_under_the_customer(self):
        """saas#1883: Meta's ``from`` of an echo is the business; the conversation is the customer's (``to``)."""
        echo = {"from": BUSINESS, "to": CUSTOMER, "id": "wamid.E", "timestamp": "1760522400", "type": "text", "text": {"body": "Sí"}}
        payload = webhook(
            "smb_message_echoes",
            {
                "messaging_product": "whatsapp",
                "metadata": {"display_phone_number": BUSINESS, "phone_number_id": PHONE_NUMBER_ID},
                "message_echoes": [echo],
            },
        )

        message = only_message(payload)

        assert (message.contact, message.body["from"], message.body["direction"]) == (CUSTOMER, CUSTOMER, "outbound")

    def test_an_echo_without_recipient_is_skipped(self):
        echo = {"from": BUSINESS, "id": "wamid.E", "timestamp": "1760522400", "type": "text", "text": {"body": "Sí"}}
        payload = webhook(
            "smb_message_echoes",
            {"metadata": {"phone_number_id": PHONE_NUMBER_ID}, "message_echoes": [echo]},
        )

        assert parse.parse(payload).messages == []


def history(*threads, **extra) -> dict:
    return webhook(
        "history",
        {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": BUSINESS, "phone_number_id": PHONE_NUMBER_ID},
            "history": [{"metadata": {"phase": 0, "chunk_order": 1, "progress": 100}, "threads": list(threads)}],
            **extra,
        },
    )


class TestTheHistoryOfTheConnection:
    def test_each_thread_files_the_customer_and_the_business(self):
        thread = {"id": CUSTOMER, "messages": [text("wamid.1", CUSTOMER, "¿Abrís?"), text("wamid.2", BUSINESS, "Sí")]}

        first, second = parse.parse(history(thread)).messages

        assert (first.body["direction"], first.body["source"], first.contact) == ("inbound", "history", CUSTOMER)
        assert (second.body["direction"], second.body["from"], second.contact) == ("outbound", CUSTOMER, CUSTOMER)

    def test_a_media_placeholder_is_marked(self):
        placeholder = {"from": CUSTOMER, "id": "wamid.M", "timestamp": "1739230970", "type": "media_placeholder"}

        (message,) = parse.parse(history({"id": CUSTOMER, "messages": [placeholder]})).messages

        assert message.placeholder is True and message.media_id == ""

    def test_the_media_follow_up_completes_by_its_id(self):
        """saas#1913: the backlog's recent media come again, with the same id, in a ``history`` change with
        ``messages`` and no threads."""
        follow_up = {
            "from": CUSTOMER,
            "id": "wamid.M",
            "timestamp": "1739230970",
            "type": "image",
            "image": {"id": "555", "mime_type": "image/jpeg"},
        }
        payload = webhook(
            "history",
            {"metadata": {"display_phone_number": BUSINESS, "phone_number_id": PHONE_NUMBER_ID}, "messages": [follow_up]},
        )

        (message,) = parse.parse(payload).messages

        assert (message.follow_up, message.media_id, message.body["source"]) == (True, "555", "history")
        assert message.body["direction"] == "inbound"

    def test_a_follow_up_of_the_business_itself_is_skipped(self):
        payload = webhook(
            "history",
            {
                "metadata": {"display_phone_number": BUSINESS, "phone_number_id": PHONE_NUMBER_ID},
                "messages": [text("wamid.O", BUSINESS, "x")],
            },
        )

        assert parse.parse(payload).messages == []

    def test_a_declined_history_is_noted_not_stored(self):
        payload = history(errors=[{"code": 2593109, "title": "History sharing declined"}])

        parsed = parse.parse(payload)

        assert parsed.messages == [] and parsed.history_declined == [PHONE_NUMBER_ID]


class TestDeliveryStatuses:
    def status(self, state, **extra) -> dict:
        return {"id": "wamid.S", "status": state, "timestamp": "1760522405", "recipient_id": CUSTOMER, **extra}

    def test_a_status_is_door_2s_body(self):
        (status,) = parse.parse(messages(statuses=[self.status("delivered")])).statuses

        assert (status.phone_number_id, status.wa_message_id, status.status) == (PHONE_NUMBER_ID, "wamid.S", "delivered")
        assert (status.error, status.status_at) == (None, "2025-10-15T10:00:05Z")

    def test_a_failure_carries_metas_code_and_reason(self):
        failed = self.status(
            "failed",
            errors=[{"code": 131047, "title": "Re-engagement message", "message": "Re-engagement message",
                     "error_data": {"details": "More than 24 hours have passed."}}],
        )

        (status,) = parse.parse(messages(statuses=[failed])).statuses

        assert status.error == {"code": "131047", "message": "Re-engagement message: More than 24 hours have passed."}

    def test_a_status_meta_does_not_name_is_skipped(self):
        parsed = parse.parse(messages(statuses=[self.status("deleted"), {"status": "sent"}]))

        assert parsed.statuses == []


class TestTemplateVerdicts:
    def test_metas_verdict_names_the_template_and_its_reason(self):
        payload = webhook(
            "message_template_status_update",
            {
                "event": "REJECTED",
                "message_template_id": 594425479261596,
                "message_template_name": "recordatorio",
                "message_template_language": "es",
                "reason": "INVALID_FORMAT",
            },
        )

        (verdict,) = parse.parse(payload).verdicts

        assert (verdict.waba_id, verdict.meta_id, verdict.name, verdict.language) == (WABA, "594425479261596", "recordatorio", "es")
        assert (verdict.status, verdict.reason) == ("REJECTED", "INVALID_FORMAT")

    def test_no_reason_reads_empty(self):
        payload = webhook(
            "message_template_status_update",
            {"event": "APPROVED", "message_template_id": 1, "message_template_name": "a", "message_template_language": "es", "reason": "NONE"},
        )

        assert parse.parse(payload).verdicts[0].reason == ""

    def test_a_new_category_is_a_verdict_too(self):
        payload = webhook(
            "template_category_update",
            {"message_template_id": 1, "message_template_name": "a", "message_template_language": "es",
             "previous_category": "UTILITY", "new_category": "MARKETING"},
        )

        (verdict,) = parse.parse(payload).verdicts

        assert (verdict.category, verdict.status) == ("MARKETING", "")


def test_the_contacts_of_the_business_app_are_not_kept():
    payload = webhook("smb_app_state_sync", {"metadata": {"phone_number_id": PHONE_NUMBER_ID}, "state_sync": [{"type": "contact"}]})

    parsed = parse.parse(payload)

    assert (parsed.messages, parsed.statuses, parsed.verdicts) == ([], [], [])


def test_a_change_without_a_number_or_of_another_kind_says_nothing():
    parsed = parse.parse(
        {"entry": [{"id": WABA, "changes": [{"field": "messages", "value": {"messages": [text()]}}, {"field": "account_update", "value": {}}]}]}
    )

    assert parsed.messages == []


def test_anything_that_is_not_metas_shape_reads_empty():
    for payload in (None, [], {"entry": "x"}, {"entry": [{"changes": "x"}]}, {"entry": [{"changes": [{"value": []}]}]}):
        assert parse.parse(payload) == parse.Parsed()


def test_metas_status_maps_to_what_the_hub_shows():
    assert [parse.hub_verdict(s) for s in ("APPROVED", "FLAGGED", "REINSTATED", "IN_APPEAL", "PAUSED", "DISABLED", "LIMIT_EXCEEDED")] == [
        "APPROVED", "APPROVED", "APPROVED", "REJECTED", "PAUSED", "DISABLED", "PENDING"
    ]
    assert parse.hub_verdict("DELETED") is None and parse.hub_verdict("PENDING_DELETION") is None
