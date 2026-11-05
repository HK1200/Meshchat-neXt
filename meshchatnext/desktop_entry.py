# SPDX-License-Identifier: 0BSD

"""Bootstrap frozen workers before importing application/network modules."""

from multiprocessing import freeze_support

if __name__ == "__main__":
    # cx_Freeze must dispatch spawned worker arguments before RNS is imported.
    # Otherwise its fallback can unpickle LXMF tasks during a partial RNS import.
    freeze_support()

    from meshchatnext.meshchat import main

    main()
