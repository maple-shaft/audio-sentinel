# Developer Conventions

## Branching

Before making any code or project file edits, create a new feature branch:

```
git checkout -b feature/<short-description>
```

Commit changes to that branch rather than directly to `master`.

## License Files

When creating a license file, always fetch the canonical text from an authoritative source using WebFetch (e.g. `https://choosealicense.com/licenses/mit/` or `https://opensource.org/license/mit`). Never generate license text from model weights.
