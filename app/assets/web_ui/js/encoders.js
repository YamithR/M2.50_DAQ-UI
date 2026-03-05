/**
 * encoders.js — Updates the ENC_H / ENC_V counter display.
 */
window.encoders = (function () {
    'use strict';

    var elH = document.getElementById('enc-h');
    var elV = document.getElementById('enc-v');

    function update(d) {
        elH.textContent = (d.enc_h >= 0 ? '+' : '') + d.enc_h;
        elV.textContent = (d.enc_v >= 0 ? '+' : '') + d.enc_v;
    }

    return { update: update };
})();
