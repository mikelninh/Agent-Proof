# EVALS

## Product eval
A useful run must answer five questions in under 60 seconds after completion:
1. How often did the agent succeed?
2. Did it make any dangerous mistakes?
3. What did each failure look like?
4. What did the agent cost and how long did it take?
5. What is the estimated economic value versus the human baseline?

A useful comparison must additionally answer:
1. Which exact cases were fixed?
2. Which exact cases regressed?
3. Did the candidate introduce any new critical failure?
4. Are the paired outcomes meaningfully different?
5. Should we PROMOTE, HOLD or REJECT the candidate?

## Engineering eval
- `pytest`
- `GET /api/health`
- 100-case baseline run produces ~87% success and BLOCK
- 100-case candidate-v2 run produces ~97% success and PASS
- baseline → candidate comparison recommends PROMOTE
- no stored run contains an API key
