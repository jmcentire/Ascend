"""
Contract-based test suite for Meeting Summarizer Interface.

Tests cover:
- Text processing functions (_truncate, _parse_json)
- Pydantic model validation (MeetingItemExtract, content validator)
- API client creation (get_client)
- API-dependent functions (summarize_transcript, extract_items, analyze_sentiment, generate_prep)
- Edge cases, error paths, and invariants

All tests use pytest with unittest.mock for dependency isolation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
import os
from typing import Any, Optional

# Import the module under test
# Adjust the import path based on actual module structure
try:
    from ascend.summarizer.interface import (
        MeetingItemKind,
        MeetingItemExtract,
        _truncate,
        _parse_json,
        content_must_be_nonempty,
        get_client,
        summarize_transcript,
        extract_items,
        analyze_sentiment,
        generate_prep,
        _MAX_INPUT_CHARS,
    )
except ImportError:
    # Fallback import for testing
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from interface import (
        MeetingItemKind,
        MeetingItemExtract,
        _truncate,
        _parse_json,
        content_must_be_nonempty,
        get_client,
        summarize_transcript,
        extract_items,
        analyze_sentiment,
        generate_prep,
        _MAX_INPUT_CHARS,
    )


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_config():
    """Create a mock AscendConfig object."""
    config = Mock()
    config.anthropic_api_key_env = "ANTHROPIC_API_KEY"
    config.model = "claude-3-opus-20240229"
    return config


@pytest.fixture
def mock_anthropic_client():
    """Create a mock Anthropic client."""
    client = Mock()
    
    # Mock the messages.create method
    mock_response = Mock()
    mock_response.content = [Mock(text="Default response")]
    client.messages.create.return_value = mock_response
    
    return client


# ============================================================================
# TESTS: _truncate
# ============================================================================

class Test_Truncate:
    """Tests for the _truncate function."""
    
    def test_truncate_happy_path_short_text(self):
        """Test _truncate with text shorter than MAX_INPUT_CHARS returns unchanged."""
        text = "This is a short text."
        result = _truncate(text)
        
        assert result == text
        assert len(result) <= _MAX_INPUT_CHARS
        assert "[TRUNCATED]" not in result
    
    def test_truncate_happy_path_long_text_with_sentence(self):
        """Test _truncate with text longer than MAX_INPUT_CHARS finds sentence boundary."""
        # Create text longer than 100k chars with sentences
        first_part = "A" * 50000
        second_part = "B" * 30000 + ". " + "C" * 20000 + "."
        text = first_part + second_part
        
        result = _truncate(text)
        
        assert "[TRUNCATED]" in result
        assert len(result) <= _MAX_INPUT_CHARS + len(" [TRUNCATED]")
    
    def test_truncate_edge_exactly_max_chars(self):
        """Test _truncate with text exactly MAX_INPUT_CHARS."""
        text = "x" * _MAX_INPUT_CHARS
        result = _truncate(text)
        
        assert len(result) == _MAX_INPUT_CHARS
        assert "[TRUNCATED]" not in result
        assert result == text
    
    def test_truncate_edge_one_over_max(self):
        """Test _truncate with text one character over MAX_INPUT_CHARS."""
        text = "x" * (_MAX_INPUT_CHARS + 1)
        result = _truncate(text)
        
        assert "[TRUNCATED]" in result
        assert len(result) <= _MAX_INPUT_CHARS + len(" [TRUNCATED]")
    
    def test_truncate_edge_empty_text(self):
        """Test _truncate with empty string."""
        text = ""
        result = _truncate(text)
        
        assert result == ""
        assert len(result) == 0
    
    def test_truncate_postcondition_length_constraint(self):
        """Test that truncate always respects length postcondition."""
        text = "x" * 200000
        result = _truncate(text)
        
        assert len(result) <= _MAX_INPUT_CHARS + len(" [TRUNCATED]")


# ============================================================================
# TESTS: _parse_json
# ============================================================================

class Test_ParseJson:
    """Tests for the _parse_json function."""
    
    def test_parse_json_happy_path_simple_object(self):
        """Test _parse_json with valid JSON object."""
        text = '{"key": "value"}'
        result = _parse_json(text)
        
        assert result == {"key": "value"}
        assert isinstance(result, dict)
    
    def test_parse_json_happy_path_with_markdown_fence(self):
        """Test _parse_json with JSON wrapped in markdown code fence."""
        text = '```json\n{"key": "value"}\n```'
        result = _parse_json(text)
        
        assert result == {"key": "value"}
    
    def test_parse_json_happy_path_with_backticks(self):
        """Test _parse_json with JSON wrapped in triple backticks without json marker."""
        text = '```\n{"key": "value"}\n```'
        result = _parse_json(text)
        
        assert result == {"key": "value"}
    
    def test_parse_json_edge_array(self):
        """Test _parse_json with JSON array."""
        text = '[1, 2, 3]'
        result = _parse_json(text)
        
        assert result == [1, 2, 3]
        assert isinstance(result, list)
    
    def test_parse_json_edge_primitive(self):
        """Test _parse_json with JSON primitive."""
        text = '42'
        result = _parse_json(text)
        
        assert result == 42
    
    def test_parse_json_edge_whitespace(self):
        """Test _parse_json strips whitespace."""
        text = '  \n\t{"key": "value"}  \n\t'
        result = _parse_json(text)
        
        assert result == {"key": "value"}
    
    def test_parse_json_error_invalid_json(self):
        """Test _parse_json with invalid JSON raises error."""
        text = '{invalid json}'
        
        with pytest.raises(json.JSONDecodeError):
            _parse_json(text)


# ============================================================================
# TESTS: MeetingItemExtract and validators
# ============================================================================

class Test_MeetingItemExtract:
    """Tests for MeetingItemExtract Pydantic model."""
    
    def test_meeting_item_extract_happy_path(self):
        """Test MeetingItemExtract model with valid data."""
        item = MeetingItemExtract(
            kind=MeetingItemKind.action_item,
            content="Follow up on budget",
            owner="Alice"
        )
        
        assert item.kind == MeetingItemKind.action_item
        assert item.content == "Follow up on budget"
        assert item.owner == "Alice"
    
    def test_meeting_item_extract_happy_path_no_owner(self):
        """Test MeetingItemExtract with optional owner as None."""
        item = MeetingItemExtract(
            kind=MeetingItemKind.decision,
            content="Approved Q4 budget",
            owner=None
        )
        
        assert item.kind == MeetingItemKind.decision
        assert item.content == "Approved Q4 budget"
        assert item.owner is None
    
    def test_meeting_item_extract_all_kinds(self):
        """Test MeetingItemExtract with all enum variants."""
        kinds = [
            MeetingItemKind.action_item,
            MeetingItemKind.decision,
            MeetingItemKind.topic,
            MeetingItemKind.concern,
            MeetingItemKind.win
        ]
        
        for kind in kinds:
            item = MeetingItemExtract(kind=kind, content="Test content")
            assert item.kind == kind
    
    def test_meeting_item_extract_error_empty_content(self):
        """Test MeetingItemExtract with empty content raises validation error."""
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError) as exc_info:
            MeetingItemExtract(
                kind=MeetingItemKind.action_item,
                content="",
                owner="Alice"
            )
        
        assert "content" in str(exc_info.value).lower()


# ============================================================================
# TESTS: get_client
# ============================================================================

class Test_GetClient:
    """Tests for the get_client function."""
    
    @patch('os.getenv')
    @patch('anthropic.Anthropic')
    def test_get_client_happy_path(self, mock_anthropic, mock_getenv, mock_config):
        """Test get_client returns Anthropic client when API key is set."""
        mock_getenv.return_value = "sk-ant-test-key"
        mock_client = Mock()
        mock_anthropic.return_value = mock_client
        
        client = get_client(mock_config)
        
        assert client is not None
        mock_getenv.assert_called_once_with("ANTHROPIC_API_KEY")
        mock_anthropic.assert_called_once_with(api_key="sk-ant-test-key")
    
    @patch('os.getenv')
    def test_get_client_error_missing_api_key(self, mock_getenv, mock_config):
        """Test get_client returns None when API key env var is not set."""
        mock_getenv.return_value = None
        
        client = get_client(mock_config)
        
        assert client is None
    
    @patch('os.getenv')
    def test_get_client_error_empty_api_key(self, mock_getenv, mock_config):
        """Test get_client returns None when API key is empty string."""
        mock_getenv.return_value = ""
        
        client = get_client(mock_config)
        
        assert client is None
    
    @patch('os.getenv')
    @patch('anthropic.Anthropic')
    def test_get_client_error_client_creation_fails(self, mock_anthropic, mock_getenv, mock_config):
        """Test get_client returns None when Anthropic client construction raises exception."""
        mock_getenv.return_value = "sk-ant-test-key"
        mock_anthropic.side_effect = Exception("Client creation failed")
        
        client = get_client(mock_config)
        
        assert client is None


# ============================================================================
# TESTS: summarize_transcript
# ============================================================================

class Test_SummarizeTranscript:
    """Tests for the summarize_transcript function."""
    
    def test_summarize_transcript_happy_path(self, mock_config, mock_anthropic_client):
        """Test summarize_transcript returns summary on successful API call."""
        raw_text = "Meeting about Q4 planning. Discussed budget allocation and team expansion."
        
        mock_response = Mock()
        mock_response.content = [Mock(text="Summary of Q4 planning meeting.")]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = summarize_transcript(raw_text, mock_config, mock_anthropic_client)
        
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
        assert result == "Summary of Q4 planning meeting."
    
    def test_summarize_transcript_error_empty_input(self, mock_config, mock_anthropic_client):
        """Test summarize_transcript returns None for empty input."""
        result = summarize_transcript("", mock_config, mock_anthropic_client)
        
        assert result is None
    
    def test_summarize_transcript_error_whitespace_only(self, mock_config, mock_anthropic_client):
        """Test summarize_transcript returns None for whitespace-only input."""
        result = summarize_transcript("   \n\t  ", mock_config, mock_anthropic_client)
        
        assert result is None
    
    def test_summarize_transcript_error_no_client(self, mock_config):
        """Test summarize_transcript returns None when client is unavailable."""
        result = summarize_transcript("Valid text", mock_config, None)
        
        assert result is None
    
    def test_summarize_transcript_error_api_failure(self, mock_config, mock_anthropic_client):
        """Test summarize_transcript returns None when API call raises exception."""
        mock_anthropic_client.messages.create.side_effect = Exception("API error")
        
        result = summarize_transcript("Valid text", mock_config, mock_anthropic_client)
        
        assert result is None
    
    def test_summarize_transcript_error_empty_response(self, mock_config, mock_anthropic_client):
        """Test summarize_transcript returns None when response text is empty."""
        mock_response = Mock()
        mock_response.content = [Mock(text="")]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = summarize_transcript("Valid text", mock_config, mock_anthropic_client)
        
        assert result is None


# ============================================================================
# TESTS: extract_items
# ============================================================================

class Test_ExtractItems:
    """Tests for the extract_items function."""
    
    def test_extract_items_happy_path(self, mock_config, mock_anthropic_client):
        """Test extract_items returns validated list of items on success."""
        raw_text = "Meeting transcript with action items"
        
        mock_response = Mock()
        mock_response.content = [Mock(text='[{"kind": "action_item", "content": "Review budget", "owner": "Alice"}]')]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = extract_items(raw_text, mock_config, mock_anthropic_client)
        
        assert isinstance(result, list)
        assert len(result) > 0
        assert result[0]["kind"] == "action_item"
        assert result[0]["content"] == "Review budget"
        assert result[0]["owner"] == "Alice"
    
    def test_extract_items_happy_path_empty_list(self, mock_config, mock_anthropic_client):
        """Test extract_items returns empty list when no items found."""
        raw_text = "Meeting with no extractable items"
        
        mock_response = Mock()
        mock_response.content = [Mock(text='[]')]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = extract_items(raw_text, mock_config, mock_anthropic_client)
        
        assert result == []
    
    def test_extract_items_error_empty_input(self, mock_config, mock_anthropic_client):
        """Test extract_items returns empty list for empty input."""
        result = extract_items("", mock_config, mock_anthropic_client)
        
        assert result == []
    
    def test_extract_items_error_no_client(self, mock_config):
        """Test extract_items returns empty list when client unavailable."""
        result = extract_items("Valid text", mock_config, None)
        
        assert result == []
    
    def test_extract_items_error_malformed_json(self, mock_config, mock_anthropic_client):
        """Test extract_items returns empty list when response is not valid JSON."""
        mock_response = Mock()
        mock_response.content = [Mock(text='invalid json')]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = extract_items("Valid text", mock_config, mock_anthropic_client)
        
        assert result == []
    
    def test_extract_items_error_not_a_list(self, mock_config, mock_anthropic_client):
        """Test extract_items returns empty list when parsed JSON is not a list."""
        mock_response = Mock()
        mock_response.content = [Mock(text='{"not": "a list"}')]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = extract_items("Valid text", mock_config, mock_anthropic_client)
        
        assert result == []
    
    def test_extract_items_edge_invalid_items_dropped(self, mock_config, mock_anthropic_client):
        """Test extract_items drops invalid items from response with warnings."""
        mock_response = Mock()
        # Mix of valid and invalid items
        mock_response.content = [Mock(text='[{"kind": "action_item", "content": "Valid"}, {"kind": "invalid_kind", "content": ""}]')]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = extract_items("Valid text", mock_config, mock_anthropic_client)
        
        # Should return a list (possibly empty or with only valid items)
        assert isinstance(result, list)


# ============================================================================
# TESTS: analyze_sentiment
# ============================================================================

class Test_AnalyzeSentiment:
    """Tests for the analyze_sentiment function."""
    
    def test_analyze_sentiment_happy_path(self, mock_config, mock_anthropic_client):
        """Test analyze_sentiment returns float score in [0.0, 1.0]."""
        raw_text = "Great meeting! Very productive."
        
        mock_response = Mock()
        mock_response.content = [Mock(text='{"score": 0.85}')]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = analyze_sentiment(raw_text, mock_config, mock_anthropic_client)
        
        assert result is not None
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0
        assert result == 0.85
    
    def test_analyze_sentiment_edge_min_score(self, mock_config, mock_anthropic_client):
        """Test analyze_sentiment with score exactly 0.0."""
        mock_response = Mock()
        mock_response.content = [Mock(text='{"score": 0.0}')]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = analyze_sentiment("Very negative meeting", mock_config, mock_anthropic_client)
        
        assert result == 0.0
    
    def test_analyze_sentiment_edge_max_score(self, mock_config, mock_anthropic_client):
        """Test analyze_sentiment with score exactly 1.0."""
        mock_response = Mock()
        mock_response.content = [Mock(text='{"score": 1.0}')]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = analyze_sentiment("Extremely positive meeting", mock_config, mock_anthropic_client)
        
        assert result == 1.0
    
    def test_analyze_sentiment_edge_clamp_below_zero(self, mock_config, mock_anthropic_client):
        """Test analyze_sentiment clamps negative scores to 0.0."""
        mock_response = Mock()
        mock_response.content = [Mock(text='{"score": -0.5}')]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = analyze_sentiment("Some text", mock_config, mock_anthropic_client)
        
        assert result == 0.0
    
    def test_analyze_sentiment_edge_clamp_above_one(self, mock_config, mock_anthropic_client):
        """Test analyze_sentiment clamps scores above 1.0."""
        mock_response = Mock()
        mock_response.content = [Mock(text='{"score": 1.5}')]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = analyze_sentiment("Some text", mock_config, mock_anthropic_client)
        
        assert result == 1.0
    
    def test_analyze_sentiment_error_empty_input(self, mock_config, mock_anthropic_client):
        """Test analyze_sentiment returns None for empty input."""
        result = analyze_sentiment("", mock_config, mock_anthropic_client)
        
        assert result is None
    
    def test_analyze_sentiment_error_no_client(self, mock_config):
        """Test analyze_sentiment returns None when client unavailable."""
        result = analyze_sentiment("Valid text", mock_config, None)
        
        assert result is None
    
    def test_analyze_sentiment_error_unparseable_response(self, mock_config, mock_anthropic_client):
        """Test analyze_sentiment returns None when response cannot be parsed."""
        mock_response = Mock()
        mock_response.content = [Mock(text='not a valid response')]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = analyze_sentiment("Valid text", mock_config, mock_anthropic_client)
        
        assert result is None
    
    def test_analyze_sentiment_error_api_failure(self, mock_config, mock_anthropic_client):
        """Test analyze_sentiment returns None on API exception."""
        mock_anthropic_client.messages.create.side_effect = Exception("API error")
        
        result = analyze_sentiment("Valid text", mock_config, mock_anthropic_client)
        
        assert result is None


# ============================================================================
# TESTS: generate_prep
# ============================================================================

class Test_GeneratePrep:
    """Tests for the generate_prep function."""
    
    def test_generate_prep_happy_path(self, mock_config, mock_anthropic_client):
        """Test generate_prep returns prep plan on success."""
        member_name = "Alice"
        recent_meetings = []
        open_items = []
        performance_data = None
        
        mock_response = Mock()
        mock_response.content = [Mock(text="Prep plan for Alice: Focus on Q4 goals.")]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = generate_prep(
            member_name, recent_meetings, open_items, performance_data,
            mock_config, mock_anthropic_client
        )
        
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Alice" in result or len(result) > 0
    
    def test_generate_prep_error_empty_member_name(self, mock_config, mock_anthropic_client):
        """Test generate_prep returns None for empty member name."""
        result = generate_prep("", [], [], None, mock_config, mock_anthropic_client)
        
        assert result is None
    
    def test_generate_prep_error_whitespace_member_name(self, mock_config, mock_anthropic_client):
        """Test generate_prep returns None for whitespace-only member name."""
        result = generate_prep("   ", [], [], None, mock_config, mock_anthropic_client)
        
        assert result is None
    
    def test_generate_prep_error_no_client(self, mock_config):
        """Test generate_prep returns None when client unavailable."""
        result = generate_prep("Alice", [], [], None, mock_config, None)
        
        assert result is None
    
    def test_generate_prep_error_api_failure(self, mock_config, mock_anthropic_client):
        """Test generate_prep returns None on API exception."""
        mock_anthropic_client.messages.create.side_effect = Exception("API error")
        
        result = generate_prep("Alice", [], [], None, mock_config, mock_anthropic_client)
        
        assert result is None
    
    def test_generate_prep_error_empty_response(self, mock_config, mock_anthropic_client):
        """Test generate_prep returns None when response text is empty."""
        mock_response = Mock()
        mock_response.content = [Mock(text="")]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = generate_prep("Alice", [], [], None, mock_config, mock_anthropic_client)
        
        assert result is None
    
    @patch('ascend.config.load_config')
    def test_generate_prep_loads_config_if_none(self, mock_load_config, mock_anthropic_client):
        """Test generate_prep loads config if not provided."""
        mock_config = Mock()
        mock_config.anthropic_api_key_env = "ANTHROPIC_API_KEY"
        mock_config.model = "claude-3-opus-20240229"
        mock_load_config.return_value = mock_config
        
        mock_response = Mock()
        mock_response.content = [Mock(text="Prep plan")]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        result = generate_prep("Alice", [], [], None, None, mock_anthropic_client)
        
        # Should have attempted to load config
        mock_load_config.assert_called_once()


# ============================================================================
# TESTS: Invariants
# ============================================================================

class Test_Invariants:
    """Tests for contract invariants."""
    
    def test_invariant_max_input_chars(self):
        """Test that _MAX_INPUT_CHARS constant is 100,000."""
        assert _MAX_INPUT_CHARS == 100000
    
    def test_invariant_graceful_degradation_summarize(self, mock_config):
        """Test that summarize_transcript returns None on failure."""
        result = summarize_transcript("", mock_config, None)
        
        assert result is None
    
    def test_invariant_graceful_degradation_extract(self, mock_config):
        """Test that extract_items returns empty list on failure."""
        result = extract_items("", mock_config, None)
        
        assert result == []
    
    def test_invariant_graceful_degradation_sentiment(self, mock_config):
        """Test that analyze_sentiment returns None on failure."""
        result = analyze_sentiment("", mock_config, None)
        
        assert result is None
    
    def test_invariant_graceful_degradation_prep(self, mock_config):
        """Test that generate_prep returns None on failure."""
        result = generate_prep("", [], [], None, mock_config, None)
        
        assert result is None
