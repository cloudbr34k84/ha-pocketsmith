# Local Development Setup

## How It Works

The repo uses the standard HACS layout where integration files live inside `custom_components/ha_pocketsmith/`. Home Assistant needs the integration folder directly under its own `custom_components/` directory, so a symlink bridges the two.

```
/homeassistant/
├── brads_dev/
│   └── ha-pocketsmith/    ← git repo (edit files here)
│       ├── custom_components/
│       │   └── ha_pocketsmith/        ← actual integration source
│       ├── tests/
│       └── ...
└── custom_components/
    └── ha_pocketsmith -> ../brads_dev/ha-pocketsmith/custom_components/ha_pocketsmith
                                       ← symlink (HA loads from here)
```

## Where to Edit

Always edit files inside the **git repo**:

```
/homeassistant/brads_dev/ha-pocketsmith/custom_components/ha_pocketsmith/
```

Changes are immediately visible to Home Assistant through the symlink — no copying needed.

## Recreating the Symlink

If the symlink is ever lost (e.g. after a container rebuild), recreate it with:

```bash
cd /homeassistant/custom_components
ln -s ../brads_dev/ha-pocketsmith/custom_components/ha_pocketsmith ha_pocketsmith
```

The relative link resolves from both `/homeassistant` in the SSH add-on and
`/config` inside the Home Assistant container.

## After Making Changes

| Change type | What to do |
|---|---|
| Python logic, sensors, coordinators | Settings → Developer Tools → Reload (or restart HA) |
| `manifest.json` or new files | Full HA restart required |
| `strings.json` / translations | Full HA restart required |

## Git Workflow

```bash
cd /homeassistant/brads_dev/ha-pocketsmith

git pull          # get latest from GitHub
# ... make changes ...
git add .
git commit -m "your message"
git push
```
