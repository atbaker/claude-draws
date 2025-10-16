// Learn more about clients at https://docs.boundaryml.com/docs/snippets/clients/overview

client<llm> CustomSonnet45 {
  provider anthropic
  options {
    model "claude-sonnet-4-5-20250929"
    api_key env.ANTHROPIC_API_KEY
  }
}

// Deterministic client for metadata extraction (temperature 0)
client<llm> DeterministicSonnet45 {
  provider anthropic
  options {
    model "claude-sonnet-4-5-20250929"
    api_key env.ANTHROPIC_API_KEY
    temperature 0
  }
}

// Creative client for prompt generation (temperature 1.0)
client<llm> CreativeSonnet45 {
  provider anthropic
  options {
    model "claude-sonnet-4-5-20250929"
    api_key env.ANTHROPIC_API_KEY
    temperature 1.0
  }
}

// https://docs.boundaryml.com/docs/snippets/clients/retry
retry_policy Constant {
  max_retries 3
  strategy {
    type constant_delay
    delay_ms 200
  }
}

retry_policy Exponential {
  max_retries 2
  strategy {
    type exponential_backoff
    delay_ms 300
    multiplier 1.5
    max_delay_ms 10000
  }
}