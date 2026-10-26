/** Inspect bounded headers before handing untrusted compressed pictures to the browser. */
export function photoDimensions(bytes, type) {
    const data = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const word = (offset) => String.fromCharCode(...bytes.subarray(offset, offset + 4));
    let width, height;
    if (type === "image/png" && bytes.length >= 24 && word(1) === "PNG\r" && word(12) === "IHDR") {
        width = data.getUint32(16);
        height = data.getUint32(20);
    } else if (type === "image/webp" && bytes.length >= 25 && word(0) === "RIFF" && word(8) === "WEBP") {
        const kind = word(12);
        if (kind === "VP8X" && bytes.length >= 30) {
            width = 1 + bytes[24] + (bytes[25] << 8) + (bytes[26] << 16);
            height = 1 + bytes[27] + (bytes[28] << 8) + (bytes[29] << 16);
        } else if (kind === "VP8L" && bytes[20] === 47) {
            const bits = data.getUint32(21, true);
            width = 1 + (bits & 16383);
            height = 1 + ((bits >>> 14) & 16383);
        } else if (kind === "VP8 " && bytes.length >= 30 && bytes[23] === 157 && bytes[24] === 1 && bytes[25] === 42) {
            width = data.getUint16(26, true) & 16383;
            height = data.getUint16(28, true) & 16383;
        }
    } else if (type === "image/jpeg" && bytes[0] === 255 && bytes[1] === 216) {
        let p = 2;
        while (p + 3 < bytes.length) {
            if (bytes[p++] !== 255) break;
            while (bytes[p] === 255) p++;
            const marker = bytes[p++];
            if (marker === 218 || marker === 217 || p + 2 > bytes.length) break;
            const length = data.getUint16(p);
            if (length < 2 || p + length > bytes.length) break;
            if ([192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207].includes(marker) && length >= 7) {
                height = data.getUint16(p + 3);
                width = data.getUint16(p + 5);
                break;
            }
            p += length;
        }
    }
    if (!width || !height || width * height > 40000000 || width / height < 1 / 6 || width / height > 6)
        throw new Error(
            "Choose a photo up to 40 megapixels, with an aspect ratio between 1:6 and 6:1. Crop or resize it first if needed."
        );
    return { width, height };
}
export async function checkPhoto(file) {
    const bytes = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(new Uint8Array(reader.result));
        reader.onerror = () => reject(new Error("Photo could not be read."));
        reader.readAsArrayBuffer(file.slice(0, 1048576));
    });
    return photoDimensions(bytes, file.type);
}
