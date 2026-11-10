# Figma Flow panels

The registered workspace UI runs in Figma’s iframe. Each panel is a React view. The native host keeps the Figma API, file and page checks, and transaction handling in the plugin sandbox. The Python compiler embeds the built JS, CSS and translated messages. A designer can use the installed package offline.

## Build

From the repository root:

```sh
npm --prefix panel-ui install --ignore-scripts --no-package-lock
npm --prefix panel-ui run build
git diff -- figma-bridge/assets
```

Commit the generated assets with their source change. CI rebuilds and compares them. License notices for the bundled React, React DOM, Scheduler and Lucide React code are included in `figma-bridge/assets`.

## Components and state

The entry point is [app.jsx](src/app.jsx). It chooses the view for the prepared task and owns locale changes. [components.jsx](src/components.jsx) provides the shell, navigation, language selection, actions, sections, notices, disclosures and thumbnail strip. Use these components in each view. Use a named import from `lucide-react` for an icon and pair it with visible text or an accessible name.

A view subscribes to native messages and renders their observed state. Keep user content and identifiers as data. A queued action, an actual readback and a verified receipt have different meanings. The host writes bounded operation metadata into file-scoped history. The local control relay saves private readback files for Codex.

## Styles and languages

[styles/index.css](src/styles/index.css) defines the cascade in order. Change the semantic palette and spacing in `tokens.css`, native-control defaults in `base.css`, and shared component styles in `components.css`. View styles cover their own layouts, such as token comparisons, project rows and candidate thumbnails. Dynamic data values can supply CSS properties for a swatch or measured spacing bar.

Put product text in the [message catalogues](../figma-bridge/locales/). Each key has Korean, English and Japanese values with the same named placeholders. Keep task titles, file/page names, user input and readback data in their original language. Use an actual generated panel to check keyboard navigation, focus, text scaling, visible status and error recovery in both themes.
