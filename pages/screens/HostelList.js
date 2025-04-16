import React, { useEffect, useState } from 'react';
import { View, FlatList, Text, Image, TouchableOpacity } from 'react-native';
import axios from 'axios';

const HostelList = ({ navigation }) => {
  const [hostels, setHostels] = useState([]);

  useEffect(() => {
    const fetchHostels = async () => {
      try {
        const res = await axios.get('http://your-api.com/api/hostels');
        setHostels(res.data);
      } catch (err) {
        console.error(err);
      }
    };
    fetchHostels();
  }, []);

  return (
    <FlatList
      data={hostels}
      keyExtractor={(item) => item._id}
      renderItem={({ item }) => (
        <TouchableOpacity onPress={() => navigation.navigate('HostelDetail', { hostelId: item._id })}>
          <View style={styles.card}>
            <Image source={{ uri: item.images[0] }} style={styles.image} />
            <Text style={styles.name}>{item.name}</Text>
            <Text style={styles.price}>₹{item.price}/night (Food included)</Text>
          </View>
        </TouchableOpacity>
      )}
    />
  );
};

const styles = {
  card: { padding: 15, margin: 10, backgroundColor: '#fff', borderRadius: 8 },
  image: { width: '100%', height: 150, borderRadius: 8 },
  name: { fontSize: 18, fontWeight: 'bold', marginTop: 8 },
  price: { color: 'green', marginTop: 4 }
};

export default HostelList;
