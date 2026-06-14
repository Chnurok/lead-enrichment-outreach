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

`This is the operator surface. It shows the dossier, the trust verdict, the ranked contact paths, the draft, and the explicit approve/reject/needs_review decision.`

The batch queue is already preloaded, so you can jump straight into a ready lead and then show the export path without extra setup.

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
