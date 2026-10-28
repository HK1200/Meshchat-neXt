// SPDX-License-Identifier: 0BSD
/** A stationary primary-pointer hold; dragging, a second finger and cancellation abort it. */
export function bindMapNodeLongPress(element, { pick, open, finish = () => {}, delay = 550, distance = 10 }) {
    if (!element?.addEventListener) return null;
    let timer,
        pending,
        fired = false;
    const cancel = () => {
        clearTimeout(timer);
        timer = undefined;
        pending = undefined;
        const wasFired = fired;
        fired = false;
        if (wasFired) finish();
    };
    const down = (event) => {
        if (pending || event.isPrimary === false) {
            cancel();
            return;
        }
        if (event.button !== 0 || event.target?.closest?.("button,input,select,textarea,a,[role=dialog],.info-popup"))
            return;
        const items = pick(event);
        if (!items?.length) return;
        pending = { id: event.pointerId, x: event.clientX, y: event.clientY };
        timer = setTimeout(() => {
            timer = undefined;
            if (pending) {
                fired = true;
                open(items);
            }
        }, delay);
    };
    const move = (event) => {
        if (
            pending &&
            (event.pointerId !== pending.id ||
                Math.hypot(event.clientX - pending.x, event.clientY - pending.y) > distance)
        )
            cancel();
    };
    const bindings = [
        ["pointerdown", down],
        ["pointermove", move],
        ["pointerup", cancel],
        ["pointercancel", cancel],
        ["lostpointercapture", cancel],
    ];
    const scope = element.ownerDocument?.defaultView;
    bindings.forEach(([name, fn]) => element.addEventListener(name, fn, true));
    const outside = bindings.filter(([name]) => name !== "pointerdown");
    outside.forEach(([name, fn]) => scope?.addEventListener(name, fn, true));
    scope?.addEventListener("blur", cancel);
    return {
        cancel,
        consume() {
            clearTimeout(timer);
            timer = undefined;
            if (pending) fired = true;
            return Boolean(pending);
        },
        dispose() {
            cancel();
            bindings.forEach(([name, fn]) => element.removeEventListener(name, fn, true));
            outside.forEach(([name, fn]) => scope?.removeEventListener(name, fn, true));
            scope?.removeEventListener("blur", cancel);
        },
    };
}
