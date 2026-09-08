"""Guard the controls and actual inference configuration in paired screening."""
from benchmark_ticket_prompts import infer, profiles
from core.model_config import DEFAULT_LOCAL_MODEL_CONFIG, TICKET_EXTRACTION_PROMPT


def test_arms_isolate_length_and_prompt_without_changing_production_defaults():
    arms = profiles(TICKET_EXTRACTION_PROMPT)
    assert arms['original_30'].max_tokens == 30
    assert arms['original_96'].system_prompt == arms['original_30'].system_prompt
    assert arms['specialized_96'].max_tokens == arms['original_96'].max_tokens == 96
    assert arms['specialized_96'].system_prompt == TICKET_EXTRACTION_PROMPT
    assert {c.temperature for c in arms.values()} == {0.0}
    assert DEFAULT_LOCAL_MODEL_CONFIG.temperature == 0.2
    assert DEFAULT_LOCAL_MODEL_CONFIG.max_tokens == 30


def test_inference_uses_selected_prompt_and_limits_with_fixed_decoding():
    calls = []

    def llm(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return {'choices': [{'text': ' NON DISPONIBILE ', 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 20, 'completion_tokens': 3}}

    config = profiles(TICKET_EXTRACTION_PROMPT)['specialized_96']
    result = infer(llm, 'ticket fittizio', 'domanda pubblica', config)
    prompt, options = calls[0]
    assert TICKET_EXTRACTION_PROMPT in prompt
    assert 'ticket fittizio' in prompt and 'domanda pubblica' in prompt
    assert options['max_tokens'] == 96
    assert options['temperature'] == 0 and options['seed'] == 42
    assert result['text'] == 'NON DISPONIBILE'
    assert result['finish_reason'] == 'stop'
