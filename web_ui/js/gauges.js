/**
 * gauges.js — IMU gauge widgets.
 *
 * Renders:
 *  - Numeric pitch / roll / yaw values (already shown in #imu-pitch/roll/yaw)
 *  - Compass rose SVG in #compass-rose (yaw)
 *
 * Uses pure SVG — no external dependencies.
 */
window.gauges = (function () {
    'use strict';

    /* ── Compass Rose ─────────────────────────────────────────────── */
    var COMPASS_SIZE = 120;
    var cx = COMPASS_SIZE / 2;
    var cy = COMPASS_SIZE / 2;
    var R  = 50;

    function buildCompass() {
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width',  COMPASS_SIZE);
        svg.setAttribute('height', COMPASS_SIZE);
        svg.setAttribute('viewBox', '0 0 ' + COMPASS_SIZE + ' ' + COMPASS_SIZE);
        svg.id = 'compass-svg';

        /* Outer ring */
        var ring = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        ring.setAttribute('cx', cx);
        ring.setAttribute('cy', cy);
        ring.setAttribute('r',  R + 4);
        ring.setAttribute('fill', 'none');
        ring.setAttribute('stroke', '#333');
        ring.setAttribute('stroke-width', '1');
        svg.appendChild(ring);

        /* Cardinal labels */
        var cardinals = [['N', 0], ['E', 90], ['S', 180], ['O', 270]];
        cardinals.forEach(function (c) {
            var angle = (c[1] - 90) * Math.PI / 180;
            var x = cx + (R + 12) * Math.cos(angle);
            var y = cy + (R + 12) * Math.sin(angle) + 4;
            var t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            t.setAttribute('x', x);
            t.setAttribute('y', y);
            t.setAttribute('text-anchor', 'middle');
            t.setAttribute('font-size', '9');
            t.setAttribute('fill', '#4b5320');
            t.setAttribute('font-family', 'Courier New');
            t.textContent = c[0];
            svg.appendChild(t);
        });

        /* Tick marks every 30° */
        for (var i = 0; i < 12; i++) {
            var ang = (i * 30 - 90) * Math.PI / 180;
            var r1  = (i % 3 === 0) ? R - 6 : R - 3;
            var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', cx + R * Math.cos(ang));
            line.setAttribute('y1', cy + R * Math.sin(ang));
            line.setAttribute('x2', cx + r1 * Math.cos(ang));
            line.setAttribute('y2', cy + r1 * Math.sin(ang));
            line.setAttribute('stroke', '#333');
            line.setAttribute('stroke-width', '1');
            svg.appendChild(line);
        }

        /* Needle group (rotated by JS) */
        var needleGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        needleGroup.id = 'compass-needle';
        needleGroup.setAttribute('transform', 'rotate(0,' + cx + ',' + cy + ')');

        var needleN = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        needleN.setAttribute('points',
            cx + ',' + (cy - R + 8) + ' ' +
            (cx - 4) + ',' + (cy + 10) + ' ' +
            (cx + 4) + ',' + (cy + 10));
        needleN.setAttribute('fill', '#d32f2f');
        needleGroup.appendChild(needleN);

        var needleS = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        needleS.setAttribute('points',
            cx + ',' + (cy + R - 8) + ' ' +
            (cx - 4) + ',' + (cy - 10) + ' ' +
            (cx + 4) + ',' + (cy - 10));
        needleS.setAttribute('fill', '#444');
        needleGroup.appendChild(needleS);

        /* Centre dot */
        var dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        dot.setAttribute('cx', cx);
        dot.setAttribute('cy', cy);
        dot.setAttribute('r',  3);
        dot.setAttribute('fill', '#888');
        needleGroup.appendChild(dot);

        svg.appendChild(needleGroup);

        /* Yaw label */
        var yawLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        yawLabel.id = 'compass-yaw-label';
        yawLabel.setAttribute('x', cx);
        yawLabel.setAttribute('y', COMPASS_SIZE - 4);
        yawLabel.setAttribute('text-anchor', 'middle');
        yawLabel.setAttribute('font-size', '9');
        yawLabel.setAttribute('fill', '#0f0');
        yawLabel.setAttribute('font-family', 'Courier New');
        yawLabel.textContent = '0.0°';
        svg.appendChild(yawLabel);

        return svg;
    }

    /* Build and insert compass */
    var compassEl = document.getElementById('compass-rose');
    var compassSvg = buildCompass();
    compassEl.appendChild(compassSvg);

    /* Cached DOM refs for numeric values */
    var elPitch = document.getElementById('imu-pitch');
    var elRoll  = document.getElementById('imu-roll');
    var elYaw   = document.getElementById('imu-yaw');

    function update(d) {
        /* Numeric values */
        elPitch.textContent = d.pitch.toFixed(1) + '°';
        elRoll.textContent  = d.roll.toFixed(1)  + '°';
        elYaw.textContent   = d.yaw.toFixed(1)   + '°';

        /* Compass needle rotation */
        var needle = document.getElementById('compass-needle');
        if (needle) {
            needle.setAttribute('transform',
                'rotate(' + d.yaw.toFixed(1) + ',' + cx + ',' + cy + ')');
        }
        var yawLbl = document.getElementById('compass-yaw-label');
        if (yawLbl) {
            yawLbl.textContent = d.yaw.toFixed(1) + '°';
        }
    }

    return { update: update };
})();
