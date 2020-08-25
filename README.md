# Editor
Edit your Kalliope config in the browser

![Alt text](/extras/screenshot.png?raw=true)
## Installation
```bash
kalliope install --git-url https://github.com/corus87/editor-neuron
```

## Features
This neuron uses the open source [Ace editor v.1.4.7](https://github.com/ajaxorg/ace) written in JavaScript.
It comes with a lot of features like syntax highlighting, themes, highlight matching and a many more.

## Options

| Parameter      | Required | Type    | Default          | Comment                                  |
|----------------|----------|---------|------------------|------------------------------------------|
| listen_ip      | No       | String  | 0.0.0.0          | The IP the editor listen on              |
| port           | No       | Int     | 8000             |                                          |
| ignore_pattern | No       | List    | None             | Files to ignore                          |
| hide_hidden    | No       | Boolean | False            | Hide hidden files in file browser        |
| dir_first      | No       | Boolean | False            | Show directories first in file browser   |
| page_title     | No       | String  | Kalliope Editor  | Page title to display                    |
| stop_server    | No       | Boolean | False            | Stop the server                          |


## Synapses example to start and stop the editor

```
  - name: "start-editor"
    signals:
      - order: "start the editor"
    neurons:
      - editor:
          listen_ip: "192.168.0.25"

  - name: "stop-editor"
    signals:
      - order: "stop the editor"
    neurons:
      - editor:
          stop_server: True
```

## Synapses example to autostart with the on_start hook

brain.yml:
```
  - name: "autostart-editor"
    signals: []
    neurons:
      - editor:
          listen_ip: "192.168.0.25"

```

settings.yml:
```
hooks:
  on_start:
     - "autostart-editor"

```

## Synapses example to ignore all python and json files

```
  - name: "autostart-editor"
    signals: []
    neurons:
      - editor:
          listen_ip: "192.168.0.25"
          ignore_pattern:
            - "*.py"
            - "*.json"

```
