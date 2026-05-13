# WebSocket Events

Real-time test progress via WebSocket.

## Connecting

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/test/{chain_id}');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

## Event Types

### test_start

Emitted when a test begins.

```json
{
  "type": "test_start",
  "chain_id": "abc123",
  "prompt_count": 5,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### prompt_start

Emitted when a prompt begins processing.

```json
{
  "type": "prompt_start",
  "chain_id": "abc123",
  "prompt_index": 0,
  "prompt_text": "Hello, world!"
}
```

### prompt_result

Emitted when a prompt completes.

```json
{
  "type": "prompt_result",
  "chain_id": "abc123",
  "prompt_index": 0,
  "provider_used": "GPT-4",
  "success": true,
  "latency_ms": 823,
  "retries_used": 0,
  "total_wait_ms": 0
}
```

### test_complete

Emitted when all prompts are done.

```json
{
  "type": "test_complete",
  "chain_id": "abc123",
  "success_rate": 0.8,
  "avg_latency_ms": 750,
  "total_prompts": 5
}
```

## JavaScript Client

```javascript
function runTest(chainId, promptCount = 5) {
  const ws = new WebSocket(`ws://localhost:8000/ws/test/${chainId}`);

  ws.onopen = () => {
    console.log('Connected to test stream');
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case 'test_start':
        console.log(`Test started: ${data.prompt_count} prompts`);
        break;
      case 'prompt_result':
        console.log(`Prompt ${data.prompt_index}: ${data.success ? '✓' : '✗'} via ${data.provider_used}`);
        break;
      case 'test_complete':
        console.log(`Test complete: ${data.success_rate * 100}% success rate`);
        ws.close();
        break;
    }
  };
}
```