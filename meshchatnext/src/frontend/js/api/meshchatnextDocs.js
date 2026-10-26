// @ts-check

/**
 * Endpoint wrappers for /api/v1/meshchatnext-docs.
 * Each function maps one HTTP call through window.api. Add new
 * endpoints here rather than inlining paths in components.
 */

import { apiPath } from "../constants";

export function getContent(...rest) {
    return window.api.get(apiPath("/meshchatnext-docs/content"), ...rest);
}
export function getList(...rest) {
    return window.api.get(apiPath("/meshchatnext-docs/list"), ...rest);
}
