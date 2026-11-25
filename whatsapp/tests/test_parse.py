"""Reading Meta's webhook: what each change means for a business, before anything is stored.

Bodies from Meta's reference (https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components and
the Embedded Signup «coexistence» webhooks).
The result is the body of the Hub's door 1 (``POST /internal/whatsapp/inbound``)
and door 2 (``/status``) without ``hub`` and the attachment's address, and the verdicts of Meta on templates.
"""

import pytest

from whatsapp import parse

PHONE_NUMBER_ID = "106540352242922"
BUSINESS = "34910000000"
CUSTOMER = "34600111222"
WABA = "102290129340398"
NULLS = dict.fromkeys(
    ["id", "title", "type", "body", "caption", "mime_type", "filename", "payload", "text", "emoji", "message_id"]
)


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
            # The profile name Meta sends next to the message reaches the inbox.
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
        assert (message.media_id, message.placeholder, message.follow_up) == ("", False, False)

    def test_each_message_carries_the_name_of_whoever_wrote_it(self):
        payload = messages(
            text("wamid.1", "1"), text("wamid.2", "2"), text("wamid.3", "3"),
            contacts=[{"profile": {"name": "Ana"}, "wa_id": "1"}, {"profile": {"name": "Luis"}, "wa_id": "2"}],
        )

        assert [message.body["contact_name"] for message in parse.parse(payload).messages] == ["Ana", "Luis", ""]

    @pytest.mark.parametrize("contact", ["x", {}, {"wa_id": CUSTOMER}, {"wa_id": CUSTOMER, "profile": "x"}])
    def test_a_contact_without_a_name_is_an_empty_one(self, contact):
        assert only_message(messages(text(), contacts=[contact])).body["contact_name"] == ""

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
        """Two questions in a row, the answer says which."""
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
        assert (message.body["reply_to"], message.body["text"]) == ("wamid.M", "10:00")

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

    def test_a_reaction_that_names_no_message_is_on_the_one_it_answers(self):
        reaction = {"from": CUSTOMER, "id": "wamid.X", "type": "reaction", "context": {"id": "wamid.T"},
                    "reaction": {"emoji": "👍"}}

        assert only_message(messages(reaction)).body["reply_to"] == "wamid.T"

    @pytest.mark.parametrize("kind", ["image", "video", "audio", "document", "sticker"])
    def test_every_kind_of_attachment_carries_its_id(self, kind):
        message = only_message(messages({"from": CUSTOMER, "id": "wamid.P", "type": kind, kind: {"id": "77"}}))

        assert (message.media_id, message.body["type"]) == ("77", kind)
        assert message.body["media"] == {"mime_type": "", "filename": "", "caption": ""}

    @pytest.mark.parametrize("kind", ["location", "contacts", "unsupported", "media_placeholder"])
    def test_a_kind_without_words_keeps_only_metas_own_message(self, kind):
        content = {"id": "1", "body": "x", "caption": "x", "payload": "x", "text": "x", "emoji": "x", "message_id": "x"}
        raw = {"from": CUSTOMER, "id": "wamid.K", "type": kind, kind: content}

        message = only_message(messages(raw))

        assert [message.body[key] for key in ("type", "text", "media", "reply", "reply_to")] == [kind, "", None, None, ""]
        assert (message.media_id, message.body["payload"]) == ("", raw)

    def test_a_message_without_its_kind_is_a_text(self):
        message = only_message(messages({"from": CUSTOMER, "id": "wamid.A", "text": {"body": "Hola"}}))

        assert (message.body["type"], message.body["text"], message.body["sent_at"]) == ("text", "Hola", None)

    @pytest.mark.parametrize(
        "content",
        [None, "x", {}, {"type": "list_reply", "list_reply": "x"}, NULLS, {"type": "list_reply", "list_reply": NULLS}],
        ids=["null", "text", "empty", "reply_not_an_object", "nulls", "reply_of_nulls"],
    )
    @pytest.mark.parametrize(
        ("kind", "reply"),
        [
            ("text", None),
            ("image", None),
            ("button", {"id": "", "title": ""}),
            ("interactive", {"id": "", "title": ""}),
            ("reaction", None),
        ],
    )
    def test_what_meta_left_out_reads_empty(self, kind, reply, content):
        message = only_message(messages({"from": CUSTOMER, "id": "wamid.A", "type": kind, kind: content, "context": "x"}))

        assert (message.body["text"], message.body["reply_to"], message.media_id) == ("", "", "")
        assert message.body["reply"] == reply
        assert message.body["media"] in (None, {"mime_type": "", "filename": "", "caption": ""})

    @pytest.mark.parametrize("raw", ["x", {"id": "wamid.N", "type": "text"}, {"from": CUSTOMER, "type": "text"}])
    def test_a_message_without_id_or_sender_is_skipped(self, raw):
        parsed = parse.parse(messages(raw))

        assert parsed.messages == []
        assert parsed.skipped == 1


class TestTheOwnersReplyFromThePhone:
    def test_an_echo_is_the_business_speaking_under_the_customer(self):
        """Meta's ``from`` of an echo is the business; the conversation is the customer's (``to``)."""
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
        assert (message.body["source"], message.body["contact_name"]) == ("live", "")

    @pytest.mark.parametrize("echo", ["x", {"from": BUSINESS, "id": "wamid.E", "type": "text", "text": {"body": "Sí"}}])
    def test_an_echo_without_recipient_is_skipped(self, echo):
        payload = webhook(
            "smb_message_echoes",
            {"metadata": {"phone_number_id": PHONE_NUMBER_ID}, "message_echoes": [echo]},
        )

        parsed = parse.parse(payload)

        assert (parsed.messages, parsed.skipped) == ([], 1)


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

    def test_a_thread_files_its_messages_under_the_customer_it_names(self):
        """Meta's ids read as text whatever they come as; a thread that names nobody files nothing."""
        named = {"id": int(CUSTOMER), "messages": [text("wamid.1")]}
        unnamed = {"messages": [text("wamid.2")]}

        parsed = parse.parse(history(named, unnamed))

        assert [(message.contact, message.body["direction"]) for message in parsed.messages] == [(CUSTOMER, "inbound")]
        assert parsed.skipped == 1

    def test_what_is_not_a_chunk_a_thread_or_a_message_is_not_read(self):
        payload = webhook(
            "history",
            {
                "metadata": {"phone_number_id": PHONE_NUMBER_ID},
                "history": ["x", {"threads": ["x", {"id": CUSTOMER, "messages": ["x", text("wamid.1")]}]}],
                "messages": ["x"],
            },
        )

        parsed = parse.parse(payload)

        assert ([message.wa_message_id for message in parsed.messages], parsed.skipped) == (["wamid.1"], 2)

    def test_a_media_placeholder_is_marked(self):
        placeholder = {"from": CUSTOMER, "id": "wamid.M", "timestamp": "1739230970", "type": "media_placeholder"}

        (message,) = parse.parse(history({"id": CUSTOMER, "messages": [placeholder]})).messages

        assert message.placeholder is True and message.media_id == ""

    def test_the_media_follow_up_completes_by_its_id(self):
        """The backlog's recent media come again, with the same id, in a ``history`` change with
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

    @pytest.mark.parametrize(
        ("display", "sender"), [(BUSINESS, BUSINESS), ("+34 910 00 00 00", BUSINESS), (BUSINESS, f"+{BUSINESS}")]
    )
    def test_a_follow_up_of_the_business_itself_is_skipped(self, display, sender):
        payload = webhook(
            "history",
            {
                "metadata": {"display_phone_number": display, "phone_number_id": PHONE_NUMBER_ID},
                "messages": [text("wamid.O", sender, "x"), text("wamid.C")],
            },
        )

        parsed = parse.parse(payload)

        assert ([message.wa_message_id for message in parsed.messages], parsed.skipped) == (["wamid.C"], 1)

    def test_without_the_business_own_number_no_follow_up_is_taken_for_its_own(self):
        payload = webhook(
            "history", {"metadata": {"phone_number_id": PHONE_NUMBER_ID}, "messages": [text("wamid.C", "ana.user")]}
        )

        assert only_message(payload).contact == "ana.user"

    def test_a_follow_up_without_its_sender_is_skipped(self):
        payload = webhook(
            "history", {"metadata": {"phone_number_id": PHONE_NUMBER_ID}, "messages": [{"id": "wamid.M", "type": "image"}]}
        )

        parsed = parse.parse(payload)

        assert (parsed.messages, parsed.skipped) == ([], 1)

    def test_a_declined_history_is_noted_not_stored(self):
        payload = history(errors=[{"code": 2593109, "title": "History sharing declined"}])

        parsed = parse.parse(payload)

        assert parsed.messages == [] and parsed.history_declined == [PHONE_NUMBER_ID]

    def test_a_chunk_that_says_it_was_declined_is_noted_too(self):
        payload = webhook(
            "history",
            {"metadata": {"phone_number_id": PHONE_NUMBER_ID}, "history": [{"errors": [{"code": 2593109}]}, {"threads": []}]},
        )

        assert parse.parse(payload).history_declined == [PHONE_NUMBER_ID]


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
        parsed = parse.parse(messages(statuses=[self.status("deleted"), {"status": "sent"}, "x"]))

        assert (parsed.statuses, parsed.skipped) == ([], 3)


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


    def test_a_verdict_that_names_no_template_is_not_one(self):
        payload = webhook("message_template_status_update", {"event": "APPROVED"})

        assert parse.parse(payload) == parse.Parsed()


def test_the_contacts_of_the_business_app_are_not_kept():
    payload = webhook("smb_app_state_sync", {"metadata": {"phone_number_id": PHONE_NUMBER_ID}, "state_sync": [{"type": "contact"}]})

    parsed = parse.parse(payload)

    assert (parsed.messages, parsed.statuses, parsed.verdicts) == ([], [], [])


def test_a_change_of_another_kind_says_nothing_whatever_it_carries():
    value = {
        "metadata": {"phone_number_id": PHONE_NUMBER_ID},
        "messages": [text()],
        "statuses": [{"id": "wamid.S", "status": "sent"}],
        "message_echoes": [{**text("wamid.E"), "to": CUSTOMER}],
        "history": [{"threads": [{"id": CUSTOMER, "messages": [text("wamid.1")]}]}],
        "errors": [{"code": 1}],
    }

    assert parse.parse(webhook("account_update", value)) == parse.Parsed()


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
