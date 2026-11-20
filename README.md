<p align="center">
  <img src="https://raw.githubusercontent.com/tsilva/waldofinder/main/logo.png" alt="waldofinder — a striped figure framed within a crowd" width="320">
  <br />
  <!-- repo-tagline:start -->
  <strong>🔎 Compare vision models searching for Waldo 🧩</strong>
  <!-- repo-tagline:end -->
</p>

<p align="center">
  <a href="https://github.com/tsilva/waldofinder/actions/workflows/ci.yml"><img src="https://github.com/tsilva/waldofinder/actions/workflows/ci.yml/badge.svg?branch=main" alt="Tests"></a>
  <a href="https://github.com/tsilva/waldofinder/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python 3.11 or newer"></a>
</p>

Waldofinder compares how vision-language models search for Waldo in the same
crowded scene. Inspect the exact images or crops sent to each model and save
your own review beside its predictions.

## Try it

Open the [hosted dashboard](https://waldofinder.tsilva.eu), load a scene you
have permission to use, and choose a search mode. In **Direct bounding box**,
each selected model receives the full image once. Click a result to inspect
its coordinates and evidence.

For a local run, follow [setup](https://github.com/tsilva/waldofinder/blob/main/docs/waldofinder-guide.md#quick-start).
The [usage guide](https://github.com/tsilva/waldofinder/blob/main/docs/usage.md) describes grid and recursive comparisons,
offline crop export, and review. See [hosting](https://github.com/tsilva/waldofinder/blob/main/docs/production-delivery.md)
for deployment.

[Waldofinder setup and comparison guide](https://github.com/tsilva/waldofinder/blob/main/docs/waldofinder-guide.md).

## License

[MIT License](https://github.com/tsilva/waldofinder/blob/main/LICENSE).
