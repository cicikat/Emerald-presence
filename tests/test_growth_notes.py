from core.growth import notes

def test_note_branches_and_eviction(sandbox,monkeypatch):
    monkeypatch.setattr("core.memory.provenance_log.append",lambda *a,**k:None)
    assert not notes.apply_note("int_a",None,source="s",char_id="c")
    assert notes.apply_note("int_a","我发现结尾要留物件",source="s",char_id="c")
    assert not notes.apply_note("int_a","我发现结尾要留物件",source="s",char_id="c")
    assert notes.apply_note("int_a","我发现开头要具体",source="s",replaces=1,char_id="c")
    assert notes.load("int_a",char_id="c")[0]["text"]=="我发现开头要具体"
    before=[{"text":f"独立技巧{i:02d}","ts":float(i),"src":"s","hits":0} for i in range(20)]
    before[0]["hits"]=5; notes._save("int_b",before,"c")
    notes.apply_note("int_b","全新方法需要清楚落点",source="new",char_id="c")
    after=notes.load("int_b",char_id="c")
    assert len(after)==20 and after[0]["hits"]==5

def test_increment_hits(sandbox,monkeypatch):
    monkeypatch.setattr("core.memory.provenance_log.append",lambda *a,**k:None)
    notes.apply_note("int_h","我发现要控制节奏",source="s",char_id="c")
    notes.increment_hits("int_h",char_id="c")
    assert notes.load("int_h",char_id="c")[0]["hits"]==1
