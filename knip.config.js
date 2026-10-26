/** @type {import("knip").KnipConfig} */
export default {
    entry: [
        "meshchatnext/src/frontend/index.html",
        "electron/preload.js",
        "meshchatnext/src/frontend/public/service-worker.js",
        "scripts/**/*.{js,mjs,cjs}",
        "tests/**/*.{js,cjs,mjs}",
    ],
    project: [
        "meshchatnext/src/frontend/**/*.{js,vue}",
        "electron/**/*.js",
        "scripts/**/*.{js,mjs,cjs}",
        "tests/**/*.{js,cjs,mjs}",
    ],
    ignore: ["meshchatnext/src/frontend/public/**", "electron/assets/**", "**/*.worklet.js"],
    ignoreDependencies: ["@tailwindcss/forms", "puppeteer-core"],
    ignoreIssues: {
        "meshchatnext/src/frontend/js/reticulumPathfinding.js": ["unlisted"],
    },
    rules: {
        binaries: "off",
        dependencies: "error",
        devDependencies: "off",
        duplicates: "error",
        exports: "off",
        files: "off",
        types: "off",
        unlisted: "error",
        unresolved: "off",
    },
};
