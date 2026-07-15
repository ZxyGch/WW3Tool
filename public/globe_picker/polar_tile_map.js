(function(global) {
  'use strict';

  var RESOLUTIONS = Array.from({ length: 19 }, function(_, level) {
    return 238810.813354 / Math.pow(2, level);
  });

  var CONFIGS = {
    north: {
      code: 'EPSG:5936',
      definition: '+proj=stere +lat_0=90 +lon_0=-150 +k=0.994 +x_0=2000000 +y_0=2000000 +datum=WGS84 +units=m +no_defs',
      extent: [-2623285.8809, -2623287.153, 6623285.8803, 6623284.6082],
      worldExtent: [-180, 45, 180, 90],
      center: [2000000, 2000000],
      origin: [-28567784.109255, 32567784.109255],
      service: 'https://services.arcgisonline.com/ArcGIS/rest/services/Polar/Arctic_Imagery/MapServer',
      attribution: 'Esri · Arctic Imagery'
    },
    south: {
      code: 'EPSG:3031',
      definition: '+proj=stere +lat_0=-90 +lat_ts=-71 +lon_0=0 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs',
      extent: [-4524537.4595, -4524537.9192, 4524539.6189, 4524539.1592],
      worldExtent: [-180, -90, 180, -45],
      center: [0, 0],
      origin: [-33699550.99203, 33699551.01703],
      service: 'https://services.arcgisonline.com/ArcGIS/rest/services/Polar/Antarctic_Imagery/MapServer',
      attribution: 'Esri · Antarctic Imagery'
    }
  };

  var dependencyPromise = null;

  function loadScript(url, globalName) {
    if (global[globalName]) return Promise.resolve();
    return new Promise(function(resolve, reject) {
      var script = document.createElement('script');
      script.src = url;
      script.onload = function() { global[globalName] ? resolve() : reject(new Error(globalName)); };
      script.onerror = function() {
        script.remove();
        reject(new Error(globalName));
      };
      document.head.appendChild(script);
    });
  }

  function loadStylesheet(url) {
    if (document.querySelector('link[data-polar-map-style]')) return;
    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = url;
    link.dataset.polarMapStyle = 'true';
    document.head.appendChild(link);
  }

  async function ensureDependencies() {
    if (!dependencyPromise) {
      loadStylesheet('https://cdn.jsdelivr.net/npm/ol@10.9.0/ol.css');
      dependencyPromise = Promise.all([
        loadScript('https://cdn.jsdelivr.net/npm/proj4@2.12.1/dist/proj4.js', 'proj4'),
        loadScript('https://cdn.jsdelivr.net/npm/ol@10.9.0/dist/ol.js', 'ol')
      ]);
    }
    try {
      await dependencyPromise;
    } catch (error) {
      dependencyPromise = null;
      throw error;
    }
  }

  function regionStyle(feature) {
    var color = feature.get('color') || '#1677d2';
    if (feature.get('kind') === 'point') {
      return new ol.style.Style({
        image: new ol.style.Circle({
          radius: 5,
          fill: new ol.style.Fill({ color: '#26a269' }),
          stroke: new ol.style.Stroke({ color: '#ffffff', width: 1.5 })
        }),
        text: new ol.style.Text({
          text: String(feature.get('label') || ''),
          offsetX: 10,
          textAlign: 'left',
          font: '600 11px system-ui, sans-serif',
          fill: new ol.style.Fill({ color: '#168451' }),
          stroke: new ol.style.Stroke({ color: 'rgba(255,255,255,0.95)', width: 3 })
        })
      });
    }
    return new ol.style.Style({
      fill: new ol.style.Fill({ color: color + '24' }),
      stroke: new ol.style.Stroke({ color: color, width: Number(feature.get('width') || 1.5) })
    });
  }

  function PolarTileMap(target) {
    this.target = target;
    this.map = null;
    this.projection = null;
    this.vectorSource = null;
    this.pole = null;
    this.attribution = '';
  }

  PolarTileMap.prototype.initialize = async function(pole) {
    await ensureDependencies();
    this.destroy();
    var config = CONFIGS[pole];
    if (!config) throw new Error('Unknown polar map: ' + pole);
    this.pole = pole;
    this.attribution = config.attribution;

    proj4.defs(config.code, config.definition);
    ol.proj.proj4.register(proj4);
    this.projection = ol.proj.get(config.code);
    this.projection.setExtent(config.extent);
    this.projection.setWorldExtent(config.worldExtent);

    var tileGrid = new ol.tilegrid.TileGrid({
      origin: config.origin,
      resolutions: RESOLUTIONS,
      tileSize: 256,
      extent: config.extent
    });
    var tileSource = new ol.source.XYZ({
      projection: this.projection,
      tileGrid: tileGrid,
      wrapX: false,
      transition: 0,
      crossOrigin: 'anonymous',
      tileUrlFunction: function(tileCoord) {
        if (!tileCoord) return undefined;
        return config.service + '/tile/' + tileCoord[0] + '/' + tileCoord[2] + '/' + tileCoord[1];
      }
    });
    this.vectorSource = new ol.source.Vector({ wrapX: false });

    var view = new ol.View({
      projection: this.projection,
      resolutions: RESOLUTIONS,
      center: config.center,
      zoom: 4,
      maxZoom: 18,
      extent: config.extent,
      constrainOnlyCenter: false,
      showFullExtent: false,
      smoothExtentConstraint: false,
      smoothResolutionConstraint: false
    });
    this.map = new ol.Map({
      target: this.target,
      controls: [],
      layers: [
        new ol.layer.Tile({ source: tileSource }),
        new ol.layer.Graticule({
          showLabels: false,
          wrapX: false,
          intervals: [30, 15],
          strokeStyle: new ol.style.Stroke({ color: 'rgba(37,101,132,0.55)', width: 1 })
        }),
        new ol.layer.Vector({ source: this.vectorSource, style: regionStyle })
      ],
      view: view
    });
    this.map.updateSize();
  };

  PolarTileMap.prototype.eventLonLat = function(event) {
    if (!this.map || !this.projection) return null;
    var bounds = this.target.getBoundingClientRect();
    var pixel = [event.clientX - bounds.left, event.clientY - bounds.top];
    var coordinate = this.map.getCoordinateFromPixel(pixel);
    if (!coordinate) return null;
    var lonLat = ol.proj.transform(coordinate, this.projection, 'EPSG:4326');
    if (!Number.isFinite(lonLat[0]) || !Number.isFinite(lonLat[1])) return null;
    if (this.pole === 'north' && lonLat[1] < 45) return null;
    if (this.pole === 'south' && lonLat[1] > -45) return null;
    return lonLat;
  };

  PolarTileMap.prototype.lonLatPixel = function(lonLat) {
    if (!this.map || !this.projection) return null;
    var coordinate = ol.proj.transform(lonLat, 'EPSG:4326', this.projection);
    var pixel = this.map.getPixelFromCoordinate(coordinate);
    if (!pixel || !Number.isFinite(pixel[0]) || !Number.isFinite(pixel[1])) return null;
    return pixel;
  };

  PolarTileMap.prototype.onViewChange = function(callback) {
    if (!this.map || typeof callback !== 'function') return;
    var view = this.map.getView();
    view.on('change:center', callback);
    view.on('change:resolution', callback);
  };

  PolarTileMap.prototype.setTool = function(tool) {
    if (!this.map) return;
    this.map.getInteractions().forEach(function(interaction) {
      if (interaction instanceof ol.interaction.DragPan) interaction.setActive(tool === 'pan');
    });
  };

  PolarTileMap.prototype.render = function(regions, points, geometryBuilder) {
    if (!this.vectorSource || !this.projection) return;
    this.vectorSource.clear(true);
    var format = new ol.format.GeoJSON();
    var projection = this.projection;
    regions.forEach(function(region) {
      var feature = format.readFeature({
        type: 'Feature',
        geometry: geometryBuilder(region.north, region.south, region.east, region.west)
      }, { dataProjection: 'EPSG:4326', featureProjection: projection });
      feature.setProperties({
        kind: 'region', color: region.color || '#1677d2', width: region.width || 1.5
      });
      this.vectorSource.addFeature(feature);
    }, this);
    points.forEach(function(point, index) {
      var coordinate = ol.proj.transform([Number(point.lon), Number(point.lat)], 'EPSG:4326', projection);
      var feature = new ol.Feature(new ol.geom.Point(coordinate));
      feature.setProperties({ kind: 'point', label: String(point.name || index) });
      this.vectorSource.addFeature(feature);
    }, this);
  };

  PolarTileMap.prototype.zoomBy = function(delta) {
    if (!this.map) return;
    var view = this.map.getView();
    view.animate({ zoom: view.getZoom() + delta, duration: 140 });
  };

  PolarTileMap.prototype.resize = function() {
    if (this.map) this.map.updateSize();
  };

  PolarTileMap.prototype.destroy = function() {
    if (!this.map) return;
    this.map.setTarget(null);
    this.map = null;
    this.vectorSource = null;
    this.projection = null;
  };

  global.PolarTileMap = PolarTileMap;
})(window);
