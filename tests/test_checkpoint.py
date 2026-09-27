from app.models.schemas import FeatureCategory, FeatureClassification, RequirementUnderstanding
from app.pipeline.checkpoint import CheckpointStore, make_run_id


def test_make_run_id_is_deterministic_and_content_sensitive():
    id1 = make_run_id("Users upload a license.", "Text")
    id2 = make_run_id("Users upload a license.", "Text")
    id3 = make_run_id("Something else entirely.", "Text")
    assert id1 == id2
    assert id1 != id3


def test_checkpoint_store_saves_and_loads_model(tmp_path):
    store = CheckpointStore(run_id="abc123", base_dir=str(tmp_path))
    assert not store.has("feature_classification")

    data = FeatureClassification(category=FeatureCategory.NEW_FEATURE, rationale="test")
    store.save("feature_classification", data)

    assert store.has("feature_classification")
    loaded = store.load("feature_classification", FeatureClassification)
    assert loaded == data


def test_checkpoint_store_saves_and_loads_text(tmp_path):
    store = CheckpointStore(run_id="abc123", base_dir=str(tmp_path))
    assert store.load_text("executive_summary") is None

    store.save_text("executive_summary", "This is the summary.")
    assert store.load_text("executive_summary") == "This is the summary."
    assert store.has("executive_summary")


def test_checkpoint_store_clear_removes_saved_data(tmp_path):
    store = CheckpointStore(run_id="abc123", base_dir=str(tmp_path))
    store.save("requirement_understanding", RequirementUnderstanding(summary="hello"))
    assert store.has("requirement_understanding")

    store.clear()
    assert not store.has("requirement_understanding")
    assert store.load("requirement_understanding", RequirementUnderstanding) is None
