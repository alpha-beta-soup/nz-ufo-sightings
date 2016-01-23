var credits, get_attribution, get_icon, map, oms, popup, ufo_icon, ufo_icon_cow;

L.mapbox.accessToken = "pk.eyJ1IjoiYWxwaGEtYmV0YS1zb3VwIiwiYSI6ImxMaVFfVTAifQ.VD93-nQ8FuT4VsPyh8LbBw";

map = L.mapbox.map('map', "alpha-beta-soup.cda5ee4e");

map.setView([-41.2889, 174.7772], 6);

ufo_icon = L.icon({
  iconUrl: './style/ufo_icon.svg',
  iconSize: [25, 25]
});

ufo_icon_cow = L.icon({
  iconUrl: './style/ufo_icon_with_cow.svg',
  iconSize: [25, 25]
});

oms = new OverlappingMarkerSpiderfier(map, {
  keepSpiderfied: true,
  circleSpiralSwitchover: Infinity,
  legWeight: 2.5
});

get_icon = function() {
  var icon;
  icon = ufo_icon;
  if (Math.random() > 0.98) {
    icon = ufo_icon_cow;
  }
  return icon;
};

oms.legColors.usual = 'red';

oms.legColors.highlighted = 'white';

popup = new L.Popup();

oms.addListener('click', function(marker) {
  popup.setContent(marker.desc);
  popup.setLatLng(marker.getLatLng());
  map.openPopup(popup);
});

oms.addListener('spiderfy', function(markers) {
  map.closePopup();
});

$.getJSON($('link[rel="ufos"]').attr('href'), function(data) {
  var sliderControl, ufos;
  ufos = L.geoJson(data, {
    onEachFeature: function(feature, layer, latlng) {
      var dateObject;
      dateObject = new Date(Date.parse(feature.properties.date.substring(0, 10)));
      layer.bindPopup('<em><span class="glyphicon glyphicon-question-sign"></span> ' + feature.properties.features.substring(0, 1).toUpperCase() + feature.properties.features.substring(1) + '<br>' + '<span class="glyphicon glyphicon-calendar"></span> ' + dateObject.toDateString() + '<br>' + '<span class="glyphicon glyphicon-time"></span>  ' + feature.properties.time + '<br>' + '<span class="glyphicon glyphicon-map-marker"></span> ' + feature.properties.location + '<br>' + '<span class="glyphicon glyphicon-link"></span> ' + '<a href="' + feature.properties.source + '"><span class="url">' + feature.properties.source + '</span></a></em><br><br>' + feature.properties.description + '<br>');
    },
    pointToLayer: function(feature, latlng) {
      var marker;
      marker = L.marker(latlng, {
        icon: get_icon()
      });
      oms.addMarker(marker);
      return marker;
    }
  });
  sliderControl = L.control.sliderControl({
    position: 'topright',
    layer: ufos,
    range: true
  });
  ufos.addTo(map);
  map.addControl(sliderControl);
  sliderControl.startSlider();
});

get_attribution = function() {
  var attribution, github, twitter, ufocus, ufocus_web;
  ufocus_web = 'http://www.ufocusnz.org.nz/';
  ufocus = 'UFOCUS NZ';
  github = 'https://github.com/alpha-beta-soup/nz-ufo-sightings';
  twitter = 'https://twitter.com/alphabeta_soup';
  attribution = "UFO data © <a href='" + ufocus_web + "'>" + ufocus + "</a>";
  attribution += " | <a href='" + github + "')>Github</a>";
  attribution += " | <a href='" + twitter + "'>Twitter</a>";
  attribution += " | Locations approximate, may be way off!";
  return attribution;
};

credits = L.control.attribution().addTo(map);

credits.addAttribution(get_attribution());
