# Third-party components in the browser arcade

## 6502.ts (emulator core)

`emulator.js` bundles the Atari 2600 core of [6502.ts](https://github.com/6502ts/6502.ts)
version 1.1.4 with the arcade's game interface (`emulator/ale.js`). 6502.ts is
distributed under the MIT license:

    Copyright (c) 2014 -- 2020 Christian Speckner and contributors

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

The bundle also carries 6502.ts's runtime dependencies (`microevent.ts`,
`seedrandom`, `tslib`), each under its own permissive license as recorded in
the bundle's legal comments.

## Game ROM images

`roms/freeway.bin` (2,048 bytes, MD5 `8e0ab801b1705a740b476b7f588c6d16`) and
`roms/atlantis.bin` (4,096 bytes, MD5 `9ad36e699ef6f45d9eb6c4cf90475c9f`) are
the ROM images shipped inside the `ale-py` 0.12.1 wheel of the Arcade Learning
Environment (Farama Foundation), the same files the Python server edition loads
through ALE. They are Activision's Freeway and Imagic's Atlantis and are
distributed here only so the demo can run the same two games.

## Game rules

The reward and terminal rules in `emulator/ale.js` follow ALE's
`games/supported/Freeway.cpp` and `Atlantis.cpp` (GPL-2.0), rewritten in
JavaScript for the two games.
