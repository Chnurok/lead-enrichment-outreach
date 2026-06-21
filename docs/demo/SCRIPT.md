# Demo script

## Short version

```bash
make demo-quick
make demo
make demo-ui
make batch-demo
make ready-export-demo
```

## Talk track

### Step 1

Command:

```bash
make demo
```

Say:

`This repo turns a company or lead list into a source-backed dossier, applies a trust gate, drafts only when the evidence is good enough, and keeps the final decision with a human.`

### Step 2

Point out the three bundled outcomes:
- `ready`: verified site plus credible contact, so draft generation is allowed
- `review_required`: weak contact evidence, so the system stops and asks for human review
- `blocked`: not enough trustworthy evidence to continue

### Step 3

Command:

```bash
make demo-ui
```

Open `http://127.0.0.1:8095`.

Say:

`This is the live browser demo. It does not just describe the product: it walks through the trust gate, the operator review step, and the approved handoff path.`

Then click in this order:
1. `Start 90-second demo`
2. `Advance guided step` if you want the UI to drive the presenter path
3. `Ready scenario`
4. `Review-required scenario`
5. `Blocked scenario`
6. back to the ready lead and the approved export path

Say:

`The ready path proves the product works. The review-required and blocked paths prove it is trustworthy. The approved export proves only reviewed leads reach downstream ops.`

### Step 4

Commands:

```bash
make batch-demo
make ready-export-demo
```

Say:

`For demos, we rebuild a deterministic batch artifact from curated fixtures, and then export only the ready leads for ops.`

## End state

If the demo lands, the viewer should remember:
- the product has a visible safety rail
- the UI is for review, not blind automation
- downstream teams get only ready leads, not noisy raw scrape output
