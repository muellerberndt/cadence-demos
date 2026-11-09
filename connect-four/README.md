# Connect Four

Play Connect Four against a deep Cadence brain (`cadence-net` 0.95.2) that settles on its move
and on its verdict of the position (loss, draw, win), and teach it a column. The page runs the
released library in your browser, in Pyodide.

```sh
python3 -m http.server 8790 --directory web   # from connect-four/; open http://localhost:8790/
```

The trained brain, its readings and the training instructions are being added to this folder.
