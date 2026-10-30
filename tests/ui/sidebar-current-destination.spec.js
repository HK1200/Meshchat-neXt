// SPDX-License-Identifier: 0BSD
const { test } = require("@playwright/test");
const { exerciseSidebarDestinationDismissal } = require("../e2e/sidebarDrawer");

test(
    "current sidebar destination dismisses the mobile drawer after Back restores it",
    exerciseSidebarDestinationDismissal
);
