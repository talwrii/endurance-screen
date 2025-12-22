# endurance-screen
If you are doing something difficult you might need some help enduring. 

This is a little tool to create a heads up display for your plan to endure. This is inspired by the expeience of planning what I am going to eat and when as an alternative to hunger cutting hard.

## Installation
You can install this with `pipx`.

```
pipx install endurance-screen.
```


## Usage
We assume that there is a local network, somewhere that you can run a service, and a screen which displays a browser connected to the screen.

I use old nexus 10 tablets which are very cheap.

You produce a plan about how you are going to endure stuff. For example, drink things etc and this gets displayed onthe screen with timers.

Run `endure-serve --host 0.0.0.0 --port 5000`  on a server.

Then on anothe client run `endure http://$IP:5000/` to update the screen or alternatively go to `http://endure:1024/edit`. Edits made to this file then get shown on the screen.



