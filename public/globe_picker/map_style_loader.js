/* 按需加载底图；行政区样式请求限时，成功结果在页面内复用。 */
(function(root) {
  'use strict';

  root.createMapStyleLoader = function(rasterStyles, optimize, timeoutMs) {
    var administrativePromise = null;

    function rasterStyle(styleId) {
      return {
        version: 8,
        sources: { 'base-tiles': rasterStyles[styleId] },
        layers: [{ id: 'base-tiles-layer', type: 'raster', source: 'base-tiles' }]
      };
    }

    async function fetchAdministrativeStyle() {
      var controller = new AbortController();
      var timer;
      try {
        var deadline = new Promise(function(_, reject) {
          timer = setTimeout(function() {
            controller.abort();
            reject(new Error('行政区底图请求超时'));
          }, timeoutMs == null ? 4000 : timeoutMs);
        });
        var request = (async function() {
          var response = await fetch(rasterStyles.administrative.style, {
            cache: 'force-cache', signal: controller.signal
          });
          if (!response.ok) throw new Error('HTTP ' + response.status);
          var style = await response.json();
          if (style.version !== 8 || !style.sources || !Array.isArray(style.layers)) {
            throw new Error('行政区底图样式无效');
          }
          return optimize(style);
        })();
        return await Promise.race([request, deadline]);
      } finally {
        clearTimeout(timer);
      }
    }

    return {
      load: async function(styleId) {
        if (styleId === 'polar') {
          return { style: { version: 8, sources: {}, layers: [] }, baseStyle: 'polar' };
        }
        if (styleId !== 'administrative') {
          return { style: rasterStyle(styleId), baseStyle: styleId };
        }
        if (!administrativePromise) {
          administrativePromise = fetchAdministrativeStyle();
          administrativePromise.catch(function() { administrativePromise = null; });
        }
        try {
          var style = await administrativePromise;
          return { style: JSON.parse(JSON.stringify(style)), baseStyle: styleId };
        } catch (_) {
          return { style: rasterStyle('light'), baseStyle: 'light', fallback: true };
        }
      }
    };
  };
})(typeof window !== 'undefined' ? window : globalThis);
