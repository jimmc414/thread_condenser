from app.pipeline.segment import segment_messages


class Msg:
    def __init__(self, platform, msg_id, text):
        self.platform = platform
        self.source_msg_id = msg_id
        self.text = text
        self.metadata_json = {"canonical_id": f"{platform}:{msg_id}"}


def test_segment_small():
    msgs = [Msg("slack", "1", "hello"), Msg("slack", "2", "world")]
    segs = segment_messages(msgs, max_tokens=1000, model="gpt-4o-mini")
    assert len(segs) == 1
    assert "hello" in segs[0] and "world" in segs[0]
