## 1.3.4
- Adapt to breaking change in youtube-dl with `info["extractor"]`.


## 1.3.2
- Ensure `strip` doesn't ever leave us with an empty file name.


## 1.3.1
- Check `youtube-dl` version as well as `youtube-multi-dl` version after running `youtube-multi-dl`, or when running `youtube-multi-dl -v`.


## 1.2.1
- Upgrade `youtube-dl` dep to 2019.04.24 because an issue appeared in 2019.2.8. You can manually upgrade the `youtube-dl` dep by running `pip3 install --upgrade youtube-dl`.


## 1.2.0
- Add version check at end of successful execution so you don't miss updates, and so you can look at these release notes.
